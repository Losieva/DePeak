# DePeak

DePeak applies diversityeffects to load profiles.
Two independent approaches are available:

- **Winter approach (Scaling)** - scales the peak directly down to a
  diversity factor (DF) calculated using Winter's approximation formula, based on user-chosen inputs (number of buildings, lower-limit parameter).
- **Shift approach** - shifts individual building profiles in time, which
  reduces the peak of the summed curve through decorrelation.

---

## Winter Approach

This approach applies a DF to an
aggregated load profile that results from summing several
building profiles without accounting for any diversity effect.

The adjusted profile satisfies two conditions that follow directly from
the definition of the diversity factor:

- **Peak reduction**: new peak = old peak × DF
- **Energy conservation**: the total energy is
  preserved exactly - diversity only changes the timing of the load, not
  the total amount of energy required.

### Calculating the GLF

The GLF can either be set directly or calculated using the empirical
approximation formula by Winter et al. (2001)[^1]:

```
GLF = a + b / (1 + (n/c)^d)
```

where `n` is the number of buildings. Only `a` (the lower asymptotic
bound of the GLF) is freely selectable; `c` and `d` are fixed at Winter's
original values. `b` is deliberately set to `1 - a` (instead of Winter's
fixed original value) so that `GLF(1) = 1` holds for any chosen `a` – with
only one building, no reduction should occur.

The formula is empirically validated only for `1 < n ≤ 200`; for larger
`n`, the tool automatically shows a note about the extrapolation.

### How the algorithm works

1. **Local peak shaving**: All local peaks and valleys are identified (a
   point counts as a peak/valley once it stands out by at least 2% of the
   total value range). Each local peak is multiplied by the GLF; the
   removed energy is redistributed proportionally to the available
   headroom across the remaining time steps of the same segment (bounded
   by the two neighboring valleys).
2. **Global correction**: If this local redistribution causes any time
   step to exceed the global target peak (peak × GLF), it is capped, and
   the excess energy is redistributed proportionally across all time
   steps below the target peak.
3. **Exact energy conservation**: Any remaining difference is distributed
   iteratively until the total energy is preserved within a tolerance of
   10⁻⁶.

### Assumptions and limitations

- The GLF itself is not calculated from the time series; it remains a
  freely chosen input parameter (`a`). `c` and `d` are fixed, `b = 1 - a`.
- Winter's formula is empirically validated only for `1 < n ≤ 200`; for
  larger `n`, the calculation extrapolates beyond the originally defined
  range.
- The two conditions above are oriented on the publicly documented
  requirements of the commercial tool
  [nPro](https://www.npro.energy/main/de/knowledge/heat-networks/diversity-factor);
  the specific energy-redistribution algorithm is an independent
  implementation and not a reconstruction of nPro's internal, non-publicly
  documented procedure.

---

## Shift Approach

Instead of directly capping peaks, this approach shifts the load peaks of
individual buildings in time. The idea: real buildings don't heat in exact
sync, but with slight individual time offsets. If the individual profiles
of several buildings are shifted randomly before summation, the peak of
the summed curve drops through the resulting decorrelation – without
prescribing a target GLF, unlike the Winter approach.

### Determining the time shift

Each of the `n` buildings receives an individual, random time offset,
drawn uniformly within a time window. The window width automatically
depends on `n` (saturation function):

```
window(n) = window_max · (1 - e^(-n/τ))
```

- `window_max` - maximum window width the user can set in the tool (default: 1 h)
- `τ` - determines how quickly the window approaches its maximum; also user-adjustable in the tool (default: 80, which works good for `n ≤ 200`)

With few buildings, the window stays small; as `n` grows, it approaches
`window_max` asymptotically, preventing unrealistically large shifts at
high building counts.

### Shifting the individual profile

The technical implementation depends on the time resolution of the input
data (60, 15, or 1 minute):

- **Hourly data (default case)**: Since hourly values don't contain any
  information about what happens *within* an hour, each profile is first
  split into much smaller time slices by smoothly filling in the values
  in between (so a shift doesn't have to jump in full-hour steps). The
  last hour of the year is treated as if it were followed by the first
  hour again, so a shift never runs off the edge of the year. After
  shifting, the fine time slices are averaged back into hours - this
  keeps the total energy exactly the same as before.
- **Finely resolved data (15 or 1 min)**: No interpolation is needed, as
  genuine sub-hour information is already present. The shift is applied
  directly on the native time grid; output resolution matches input
  resolution.

### Assumptions and limitations

- `window_max` and `τ` are both adjustable in the tool. The defaults
  (`window_max = 1 h`, `τ = 80`) reflect the assumption that shifts beyond
  one hour are no longer plausible, and that the approach should cover an application range up to roughly
  200 buildings - but users can change both values to fit their own
  use case.
- The approach only works with separate individual building profiles, not
  with an already-aggregated summed profile – the decorrelation arises
  precisely because each profile is shifted individually before summation.
- The Shift approach captures only a single mechanism of the diversity
  effect (temporal spread) and typically yields a considerably more
  moderate peak reduction than the Winter approach. It should be
  understood as a complementary, exploratory method rather than an
  independently validated alternative for determining a diversity factor.

---

[^1]: W. Winter, T. Haslauer, I. Obernberger, "Untersuchungen der
    Gleichzeitigkeit in kleinen und mittleren Nahwärmenetzen",
    Euroheat & Power, 09&10/2001.
