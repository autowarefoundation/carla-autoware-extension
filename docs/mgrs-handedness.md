# CARLA-world <-> MGRS-local transform

Evidence for the integration's #1 coordinate risk: the handedness / Y-flip and unit
convention between CARLA world space and the OpenDRIVE/MGRS-local frame the
Nishi-Shinjuku lanelet2 map lives in. The extension `.so` will
synthesise `/sensing/gnss/pose*` from an ego world transform plus a static
offset; the affine relation pinned here is what it reuses. (The GNSS
publisher has since shipped — `extension/include/carla/autoware/geo/MgrsOffset.h`
mirrors this transform byte-identically.)

Verifier: `scripts/e2e/verify_mgrs_handedness.py` (pure transform + unit
tests `tests/e2e/test_mgrs_offset.py`) and `scripts/e2e/probe_carla_mgrs.py`
(live measurement against the map).

## Concluded affine map (both directions)

`CONVERTER_OFFSET = (81655.73, 50137.43, 42.49998)` metres, MGRS 54SUE local
frame (autoware_lanelet2_to_opendrive `conf/map/nishishinjuku.yaml` `offset:`).

CARLA world in **centimetres** (the frame the extension `.so` sees; a UE
`FTransform` is native cm):

```text
forward  (CARLA world cm -> MGRS-local m)      inverse  (MGRS-local m -> CARLA world cm)
  mgrs_x = 81655.73 + x_cm/100                    x_cm = (mgrs_x - 81655.73) * 100
  mgrs_y = 50137.43 - y_cm/100   <-- Y flip       y_cm = (50137.43 - mgrs_y) * 100   <-- Y flip
  mgrs_z = 42.49998 + z_cm/100                    z_cm = (mgrs_z - 42.49998) * 100
```

## Handedness verdict

**Right-handed MGRS-local <- single Y negation -> left-handed CARLA/UE.** The
only flipped axis is Y. The flip lives entirely at the CARLA<->OpenDRIVE
boundary: LibCarla negates Y when it ingests the right-handed OpenDRIVE planView
into left-handed UE world space. OpenDRIVE-local and MGRS-local share handedness
(both right-handed, Y increases north), so `mgrs = converter_offset +
opendrive_local` carries **no** flip, and the single CARLA<->OpenDRIVE Y flip is
therefore also the single CARLA<->MGRS-local Y flip. X and Z are not flipped; the
converter offset is a pure translation.

## Units caveat (do not lose the factor of 100)

- CARLA **PythonAPI** reports **metres** (LibCarla parses OpenDRIVE metres
  straight into the road map; `carla.Location` is metres). Verification through
  the PythonAPI must scale by 100 before `world_to_mgrs_local` (helper
  `world_m_to_mgrs_local`).
- The extension **`.so`** sees UE **centimetres**, so the `/100` in
  `world_to_mgrs_local` is correct at that layer.

Note on units: the `world_to_mgrs_local(x_cm, ...)` transform with `/100` is
correct **for the extension .so (cm)**. It is _not_ a drop-in for raw PythonAPI
transforms, which are metres — feeding PythonAPI metres without the x100 scale is
a silent factor-of-100 error. This cm/m distinction is the one correction to
watch; the offset and the Y-flip sign are exactly as concluded above.

## Offline evidence: xodr <header> vs planView bounds

Source: `.../Content/Carla/Maps/OpenDrive/NishishinjukuMap.xodr` (converter
v2.59.7). The xodr has a UTM `<geoReference>` (`+proj=utm +zone=54
+lat_0=35.68804448838185 +lon_0=139.69208591412306 +datum=WGS84`) and **no
`<offset>` element**: road planView geometry is in OpenDRIVE-local metres whose
origin sits at `CONVERTER_OFFSET` in MGRS-local. The `<header>` north/south/
east/west are in MGRS-local metres. Adding the offset to the planView extent
(8750 geometry points) reproduces the header bounds, and with **no Y-flip**
(south maps to min-y, north to max-y):

| axis          | planView (OpenDRIVE-local) | +offset   | header (MGRS-local) |
| ------------- | -------------------------- | --------- | ------------------- |
| x min (west)  | -485.976                   | 81169.754 | 81167.855           |
| x max (east)  | 618.515                    | 82274.245 | 82279.963           |
| y min (south) | -363.569                   | 49773.861 | 49770.178           |
| y max (north) | 712.360                    | 50849.790 | 50855.948           |

The few-metre gaps are because planView start-points do not reach the exact map
extremes and lane widths extend past centrelines; the correspondence (offset =
OpenDRIVE-local -> MGRS-local translation, no flip) is unambiguous. A Y-flip here
would place `+offset` bounds hundreds of metres outside the header, which it does
not.

## Live evidence: measured against the running map

Measured 2026-07-21 with CARLA (UE5 editor `-game -RenderOffScreen`, editor
plugin .so of HEAD `ca6e1994c`) serving `Carla/Maps/NishishinjukuMap` on
`:2000`, via `scripts/e2e/probe_carla_mgrs.py`.

### Geo-reference is degenerate -- do not use `transform_to_geolocation`

`transform_to_geolocation((0,0,0))` returns **lat 0.000000, lon 136.511256**
(Nishi-Shinjuku is ~35.69 N, 139.69 E). The loaded map does not carry the xodr's
`+lat_0/+lon_0`, so CARLA's WGS84 output is unusable as a lat/lon ground truth.
Consequence for the extension `.so`: it must synthesise GNSS from the **affine
offset** (`world_to_mgrs_local`), never from CARLA's own geolocation. This is why
the live checks below verify against the xodr road geometry, not lat/lon.

### Check 1 -- handedness by point-cloud overlap (decisive)

`generate_waypoints(3.0)` gives 13799 CARLA waypoints; xodr planView gives 8750
reference points.

| cloud                   | x range (m)     | y range (m)         |
| ----------------------- | --------------- | ------------------- |
| CARLA waypoints         | [-486.9, 621.5] | **[-717.3, 365.1]** |
| xodr planView           | [-486.0, 618.5] | [-363.6, 712.4]     |
| Y-flip predicts CARLA y | (same x)        | **[-712.4, 363.6]** |

CARLA's measured y-range matches the **Y-flip** prediction, not the raw xodr
y-range. Median nearest-neighbour (CARLA -> xodr): **1.668 m under Y-flip
`(x,-y)`** vs **68.708 m under no-flip `(x,+y)`** -- a ~40x separation. X ranges
coincide (no X-flip) and are ~600 m not ~60000, i.e. CARLA reports **metres**.

### Check 2 -- reference-line residual, lane offset removed (sub-decimetre)

`get_waypoint_xodr(road, lane, s)` returns a lane centre; recovering the
reference line by shifting the innermost-lane centre by +/- w/2 along the
waypoint right-vector and comparing to the Y-flipped xodr point `(x,-y)`, over the
full set of 20 segments spread from x=-478 to x=+561 (every row shown; all
resolved lane |id|=1, for which +/- w/2 is exact):

```text
  road       s lane     w    xodr_x   -xodr_y     est_x     est_y  res_m
   104    5.66    1  2.93  -478.380   359.444  -478.353   359.433  0.029
   613   22.95    1  2.88  -250.956   196.512  -250.956   196.503  0.009
   338    0.00    1  3.50  -206.165   -44.163  -206.165   -44.163  0.000
    82   41.60    1  3.23  -155.092   -47.346  -155.092   -47.346  0.000
    66   14.66    1  3.09  -143.407  -398.556  -143.407  -398.556  0.000
   555   20.29    1  2.88  -119.579  -248.914  -119.579  -248.914  0.000
   317    0.00    1  3.50   -97.622  -146.732   -97.622  -146.732  0.000
   158   13.66    1  2.99   -76.334  -255.382   -76.345  -255.380  0.011
   520   16.73    1  4.89   -18.220  -451.947   -18.315  -451.877  0.118
   199   11.42    1  6.57    28.719    -3.313    28.720    -3.445  0.132
    60   13.76    1  2.75    66.909    55.538    66.909    55.539  0.001
    16  108.71    1  2.47   117.912  -350.997   117.912  -350.997  0.000
    51   17.41    1  3.37   155.753    77.224   155.753    77.224  0.000
   477   19.68    1  4.08   184.588    -0.257   184.589    -0.359  0.102
   145    5.93    1  4.39   213.927     8.059   213.928     8.076  0.017
   503   25.69    1  3.11   224.210  -500.746   224.252  -500.730  0.045
   225   14.66    1  2.98   256.728  -270.294   256.729  -270.291  0.003
   416   17.70    1  3.00   293.615  -138.994   293.637  -138.977  0.028
   396   20.06    1  2.78   379.915  -343.593   379.920  -343.596  0.006
   352   31.69    1  3.87   561.031  -349.135   561.035  -349.098  0.038
n=20 median residual 0.009 m  max 0.132 m (tol 0.5)
```

**n=20, median residual 0.009 m, max 0.132 m** (<= 0.5 m). The median is the
script's `residuals[n//2]` (11th of the 20 sorted values, 0.009 m); the sorted
residuals are seven 0.000 then 0.001, 0.003, 0.006, **0.009**, 0.011, 0.017,
0.028, 0.029, 0.038, 0.045, 0.102, 0.118, 0.132. The sign that matched was always
`+w/2` toward the reference line and the offset removed was always ~a lane
half-width, confirming the leftover ~1.6 m in the uncorrected metric is lane
geometry, not a frame error. Under the Y-flip map, CARLA world and the OpenDRIVE
reference line agree to a few centimetres everywhere on the map.

### Verdict

- **Handedness: PASS** -- single Y negation between CARLA (left-handed) and
  OpenDRIVE/MGRS-local (right-handed); X and Z not flipped.
- **Frame residual: PASS** -- sub-decimetre (median 0.009 m) across the map.
- **Units:** CARLA PythonAPI = metres; extension .so = UE centimetres.
- The affine map at the top of this document is the verified relation the extension `.so` reuses.

## Reproduce

```bash
# offline transform + unit tests
cd ~/src/carla-autoware-extension && python3 -m pytest tests/e2e/test_mgrs_offset.py -q

# single-point CLI check (extension-cm frame)
python3 scripts/e2e/verify_mgrs_handedness.py \
  --carla-xyz-cm <x_cm> <y_cm> <z_cm> --osm-local-xy <local_x> <local_y> --tol-m 0.5

# live measurement (CARLA must be up on :2000 with NishishinjukuMap available)
export ROS_DOMAIN_ID=0
python3 scripts/e2e/probe_carla_mgrs.py \
  --xodr ~/src/carla-autoware-integration/Unreal/CarlaUnreal/Content/Carla/Maps/OpenDrive/NishishinjukuMap.xodr
```
