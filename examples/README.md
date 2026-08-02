# Examples

Example scripts and usage demonstrations for AET.

## Realistic test drawings from `agl-drawing`

The private companion repository
[`mohammed5150/agl-drawing`](https://github.com/mohammed5150/agl-drawing)
generates DXF extracts of real as-built AGL layouts (AUH AGL Layout with its
original AutoCAD layers: `ADB_TAXICL`, `ADB_STOPBAR`, `EL-LEAD-IN`,
`EL-HOLDING`, the `LIC/SBC/TCC` circuits, …). Use it to produce realistic
inputs for the AET pipeline instead of hand-made fixtures:

```bash
git clone git@github.com:mohammed5150/agl-drawing.git
cd agl-drawing
git lfs install && git lfs pull          # as-built bases are LFS objects
pip install -e ".[pdf,cad]"
agl-draw validate

# DXF extract around a named location, original layers preserved
agl-draw export-dxf --airport auh "stand 201" --margin 700
# -> output/AUH-201.dxf

# Run it through AET
aet run --name "AUH Stand 201" output/AUH-201.dxf
```

Reference run (AUH stand 201, margin 700): ~72,700 entities on 105 layers
interpret cleanly in roughly 12 seconds with zero skipped entities.

Note the extract's coordinate system: one DXF unit is one base-map pixel
(origin bottom-left, Y up) — a geometry extract, not a survey drawing.
Generated DXF files are large; keep them out of version control.
