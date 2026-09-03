"""
Diversity Factor Tool
=====================
Wendet einen Diversity Factor (Gleichzeitigkeitsfaktor) auf ein
aggregiertes Lastprofil an - unter den zwei Randbedingungen, die nPro
selbst für sein Verfahren dokumentiert (nPro-Doku, "Diversity factors
in heat networks"):
  RB 1: Der neue Peak = alter Peak x Diversity Factor
  RB 2: Die Jahresenergie (Fläche unter der Kurve) bleibt gleich
Der Diversity Factor selbst wird NICHT aus den Zeitreihen berechnet. Stattdessen bleibt er, wie in nPro, ein
offener, vom Nutzer zu wählender Parameter:
  - entweder direkt als Zahl,
  - oder über Winters Näherungsformel GLF(n) = a + b/(1+(n/c)^d),
    wobei nur `a` (der Grenzwert für n -> unendlich) frei wählbar
    bleibt und b, c, d auf Winters Originalwerten fixiert sind.
"""

import numpy as np
import pandas as pd


class DiversityFactorTool:
    """
    Diversity-Factor-Anwendung auf aggregierte Lastprofile, nach
    Winters Näherungsfunktion:

        GLF(n) = a + b / (1 + (n/c)^d)

    b, c, d sind auf Winters Originalwerten fixiert (siehe Kapitel
    3.5.1). Einzig `a` - der Grenzwert von GLF(n) für n -> unendlich -
    bleibt bewusst ein offener, frei wählbarer Parameter, genau wie
    das "Lower limit of diversity factor (n -> infinity)"-Feld in
    nPros Netzwerk-Konfiguration:

        tool = DiversityFactorTool(a=0.4497)   # Winters Originalwert

    Hinweis zur Gültigkeit: Winters Formel wurde nur für 1 < n <= 200
    empirisch abgesichert. Die Formel selbst ist aber für beliebiges
    n > 0 mathematisch definiert; für n > 200 handelt es sich um eine
    Extrapolation. Winter et al. haben diese Extrapolation selbst an
    einem realen Netz mit n=255 getestet (Formel: GLF~0.47, gemessen:
    GLF=0.51) und als "plausibel" bewertet - eine Garantie ist das
    aber nicht.
    """

    # Winters Originalwerte für a, b, c, d
    A_WINTER = 0.449677646267461
    B_WINTER = 0.551234688
    C_WINTER = 53.84382392
    D_WINTER = 1.762743268

    def __init__(self, a, b=None, c=None, d=None):
        self.a = a
        # b default = 1-a, NICHT Winters fixer Wert B_WINTER.
        # Winters a und b wurden gemeinsam so gefittet, dass a+b = 1
        # gilt (Randbedingung GLF(1)=1). Wird nur a frei geändert und
        # b bleibt auf Winters Original-Wert fixiert, kann GLF(n) > 1
        # herauskommen (unphysikalisch - eine Erhöhung statt Reduktion).
        # Mit b=1-a bleibt GLF(1)=1 für jedes gewählte a erhalten.
        self.b = b if b is not None else (1 - a)
        self.c = c if c is not None else self.C_WINTER
        self.d = d if d is not None else self.D_WINTER

    # Diversity Factor für n Gebäude bestimmen

    def get_diversity_factor(self, n):
        """
        Berechnet GLF(n) nach Winters Formel mit dem gewählten `a`.

        Gibt eine Warnung aus, wenn n außerhalb des von Winter
        empirisch abgesicherten Bereichs (1 < n <= 200) liegt.
        """
        if n > 200:
            print(
                f"Hinweis: n={n} liegt außerhalb des von Winter et al. "
                f"empirisch abgesicherten Bereichs (1 < n <= 200). "
                f"Ergebnis ist eine Extrapolation."
            )

        return self.a + self.b / (1 + (n / self.c) ** self.d)

    # Anwendung auf ein aggregiertes Profil

    def apply(self, profiles, n=None, prominence=None,
              max_iterations=200, tolerance=1e-6):
        """
        Wendet den Diversity Factor auf eine Gruppe von Lastprofilen an.

        profiles: Liste von pandas.Series (ein Profil pro Gebäude,
                   gleiche Länge, gleiche stündliche Auflösung) ODER
                   eine bereits aggregierte pandas.Series (Summenkurve).

        n: Anzahl der Gebäude/Profile, benötigt für Winters Formel.
           Wird automatisch aus len(profiles) übernommen, falls eine
           Liste übergeben wird; bei einer bereits aggregierten Serie
           muss n explizit angegeben werden.

        prominence: Mindest-"Ausgeprägtheit", ab der ein lokales
                    Maximum/Minimum als Peak/Tal erkannt wird (an
                    scipy.signal.find_peaks übergeben). Wenn nicht
                    angegeben (None, Standard), wird automatisch ein
                    sinnvoller Wert relativ zur Datenspanne berechnet
                    (2% von max-min) - das funktioniert unabhängig
                    vom Maßstab der Eingabedaten (kW, normierte
                    Einheiten, etc.). Ein expliziter Wert überschreibt
                    diese automatische Berechnung.

        Rückgabe: pandas.Series - das diversity-korrigierte Profil.
                   Erfüllt exakt die zwei von nPro dokumentierten
                   Randbedingungen:
                   (1) neuer Jahres-Peak = alter Jahres-Peak x Diversity Factor
                   (2) Jahresenergie bleibt exakt erhalten

        Wichtiger Vorbehalt: Auch dieser Ansatz ist eine plausible
        Annäherung, keine bestätigte Rekonstruktion von nPros internem
        Algorithmus (der nicht öffentlich dokumentiert ist).
        """
        from scipy.signal import find_peaks

        if isinstance(profiles, (list, tuple)):
            n = n or len(profiles)
            summed = pd.concat(profiles, axis=1).sum(axis=1).astype(float)
        else:
            summed = profiles.astype(float).copy()

        diversity_factor = self.get_diversity_factor(n)
        vals = summed.to_numpy(copy=True)
        num_hours = len(vals)
        original_sum = vals.sum()
        target_peak = vals.max() * diversity_factor

        if prominence is None:
            data_range = vals.max() - vals.min()
            prominence = 0.02 * data_range

        peak_idx, _ = find_peaks(vals, prominence=prominence)

        peak_idx, _ = find_peaks(vals, prominence=prominence)
        valley_idx, _ = find_peaks(-vals, prominence=prominence)
        boundaries = np.sort(np.concatenate(([0], valley_idx, [num_hours - 1])))

        adjusted = vals.copy()

        # Schritt 1: Jeden lokalen Peak mit dem Diversity Factor reduzieren.
        # Die dabei entfernte Energie wird proportional zum verfügbaren Headroom innerhalb des jeweiligen lokalen Abschnitts zwischen zwei benachbarten Minima zurückverteilt.
        for p in peak_idx:
            left_candidates = boundaries[boundaries < p]
            right_candidates = boundaries[boundaries > p]
            left = left_candidates[-1] if len(left_candidates) else 0
            right = right_candidates[0] if len(right_candidates) else num_hours - 1

            old_val = vals[p]
            new_val = old_val * diversity_factor
            shave = old_val - new_val
            adjusted[p] = new_val

            segment_idx = [i for i in range(left + 1, right) if i != p]
            if len(segment_idx) > 0:
                segment_vals = vals[segment_idx]
                headroom = np.clip(new_val - segment_vals, 0, None)
                if headroom.sum() > 0:
                    weights = headroom / headroom.sum()
                    adjusted[segment_idx] += shave * weights
                else:
                    adjusted[segment_idx] += shave / len(segment_idx)

        # Schritt 2: Finale Peak-Korrektur.
        # Falls durch die lokale Energieumverteilung einzelne Stunden den globalen Zielpeak überschreiten, werden sie begrenzt und die überschüssige Energie proportional auf Stunden unterhalb des
        # Zielpeaks umverteilt. 
        for _ in range(max_iterations):
            over = adjusted > target_peak
            if not over.any():
                break
            excess = (adjusted[over] - target_peak).sum()
            adjusted[over] = target_peak
            below = ~over
            headroom = np.clip(target_peak - adjusted[below], 0, None)
            if headroom.sum() <= 0:
                break
            weights = headroom / headroom.sum()
            adjusted[below] += excess * weights

        # Schritt 3: Finale Korrektur zur exakten Erhaltung der Jahresenergie. Eine verbleibende Energiedifferenz wird proportional auf Stunden unterhalb des Zielpeaks verteilt.
        # Falls dabei erneut Überschreitungen entstehen, werden diese nochmals begrenzt und die überschüssige Energie umverteilt.
        for _ in range(max_iterations):
            energy_gap = original_sum - adjusted.sum()
            if abs(energy_gap) < tolerance:
                break
            below = adjusted < target_peak
            headroom = np.clip(target_peak - adjusted[below], 0, None)
            if headroom.sum() <= 0:
                break
            weights = headroom / headroom.sum()
            adjusted[below] += energy_gap * weights

            over = adjusted > target_peak
            if over.any():
                excess = (adjusted[over] - target_peak).sum()
                adjusted[over] = target_peak
                below2 = ~over
                headroom2 = np.clip(target_peak - adjusted[below2], 0, None)
                if headroom2.sum() > 0:
                    adjusted[below2] += excess * (headroom2 / headroom2.sum())

        return pd.Series(adjusted, index=summed.index)

