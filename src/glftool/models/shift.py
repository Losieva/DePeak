"""
Diversity-Factor-Tool: Zeitverschiebungs-Ansatz 
=================================================================
Alternative zum Skalierungs-Ansatz (DiversityFactorTool2 / Winters
Formel): Anstatt Peaks direkt zu kappen und Energie proportional
umzuverteilen, wird jedes Einzelgebäude-Profil um einen individuellen
Zeitversatz innerhalb eines fixen Fensters verschoben.
Durch die Dekorrelation der Einzelprofile sinkt der Peak der
Summenkurve - ohne dass ein Ziel-GLF vorgegeben wird.

RB2 (Jahresenergie bleibt erhalten) ist bei diesem Ansatz PRO
GEBÄUDE automatisch erfüllt: eine Verschiebung
verändert nur die zeitliche Verteilung eines Profils, nicht seine
Summe. Da dies für jedes Einzelprofil gilt, gilt es auch für die
Summe aller Profile.

Wichtige Einschränkung gegenüber DiversityFactorTool2:
  Dieser Ansatz funktioniert NUR mit separaten Einzelgebäude-Profilen,
  nicht mit einem bereits aggregierten Summenprofil. Der gesamte
  Diversity-Effekt entsteht dadurch, dass jedes Einzelprofil VOR der
  Summierung individuell verschoben wird. Liegt nur
  die fertige Summenkurve vor, gibt es nichts mehr, was einzeln
  verschoben werden könnte - eine Verschiebung des bereits
  aggregierten Profils würde lediglich die gesamte Kurve zeitlich
  versetzen, ohne den Peak zu reduzieren.
"""

import numpy as np
import pandas as pd

def default_window(n, window_max=1, tau=80):
    """
    Automatische Bestimmung der Fenstergröße in Abhängigkeit von n.
    Saettigungsfunktion:
 
        window(n) = window_max * (1 - exp(-n / tau))
 
    window_max: Obergrenze des Fensters (Stunden). Über diesen Wert hinaus ist eine
                Verschiebung des Heizlast-Peaks kaum noch mit
                Nutzerverhalten.
    tau:     Geschwindigkeit der Saettigung - bei n=tau ist
                ca. 63% von window_max erreicht. 
    """
    return window_max * (1 - np.exp(-n / tau))

class DiversityFactorShiftTool:
    """
    window_hours: Gesamtbreite des Verschiebungsfensters (Stunden).
    distribution: "random"  - jedes Gebäude bekommt einen zufälligen,
                               gleichverteilten Shift im Fenster.
    seed: Zufalls-Seed für Reproduzierbarkeit (nur bei "random").
    fine_steps_per_hour: Auflösung des internen Hilfsgitters für die
                  Sub-Stunden-Verschiebung. Höher = feinere/genauere Verschiebung,
                  aber mehr Rechenaufwand.
    """

    _ALLOWED_RESOLUTIONS = (60, 15, 1)
 
    def __init__(self, window_hours=None, seed=None,
                 input_resolution_minutes=60, fine_steps_per_hour=12,
                 window_max=1, tau=80):
        if input_resolution_minutes not in self._ALLOWED_RESOLUTIONS:
            raise ValueError(
                f"input_resolution_minutes muss eines von "
                f"{self._ALLOWED_RESOLUTIONS} sein (Minuten), "
                f"nicht {input_resolution_minutes}."
            )
        self.window_hours = window_hours
        self.seed = seed
        self.input_resolution_minutes = input_resolution_minutes
        self.fine_steps_per_hour = fine_steps_per_hour
        self.window_max = window_max
        self.tau = tau

    # Zeitversatz pro Gebäude bestimmen

    def _generate_shifts(self, n_buildings):
        if self.window_hours is None:
            window = default_window(n_buildings, self.window_max, self.tau)
        else:
            window = self.window_hours
        half_window = window / 2
        rng = np.random.default_rng(self.seed)
        shifts_hours = rng.uniform(-half_window, half_window, size=n_buildings)
        return shifts_hours, window

    # Einzelnes Profil um shift_hours verschieben 

    def _shift_profile(self, profile, shift_hours):
        vals = profile.to_numpy(dtype=float)
 
        if self.input_resolution_minutes == 60:
            n_hours = len(vals)
            fine_n = n_hours * self.fine_steps_per_hour
 
            x_fine = np.arange(fine_n) / self.fine_steps_per_hour
            vals_periodic = np.concatenate([vals, vals[:1]])
            x_coarse_periodic = np.arange(n_hours + 1)
            fine_vals = np.interp(x_fine, x_coarse_periodic, vals_periodic)
 
            shift_steps = int(round(shift_hours * self.fine_steps_per_hour))
            shifted_fine = np.roll(fine_vals, shift_steps)
 
            shifted_hourly = shifted_fine.reshape(n_hours, self.fine_steps_per_hour).mean(axis=1)
            return pd.Series(shifted_hourly, index=profile.index)
 
        else:
            steps_per_hour = 60 / self.input_resolution_minutes
            shift_steps = int(round(shift_hours * steps_per_hour))
            shifted = np.roll(vals, shift_steps)
            return pd.Series(shifted, index=profile.index)

    # Anwendung auf eine Gruppe von Einzelgebäude-Profilen

    def apply(self, profiles):
        n = len(profiles)
        shifts_hours, window_used = self._generate_shifts(n)
 
        shifted_profiles = [
            self._shift_profile(p, s) for p, s in zip(profiles, shifts_hours)
        ]
 
        original_sum = pd.concat(profiles, axis=1).sum(axis=1)
        adjusted = pd.concat(shifted_profiles, axis=1).sum(axis=1)
 
        effective_glf = adjusted.max() / original_sum.max()
 
        info = {
            "n_buildings": n,
            "shifts_hours": shifts_hours,
            "window_hours": window_used,
            "window_hours_auto": self.window_hours is None,
            "input_resolution_minutes": self.input_resolution_minutes,
            "effective_glf": effective_glf,
            "peak_original": original_sum.max(),
            "peak_shifted": adjusted.max(),
            "sum_original": original_sum.sum(),
            "sum_shifted": adjusted.sum(),
        }
        return adjusted, shifted_profiles, info
    
