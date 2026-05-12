"use client";

// Hand-rolled SVG radar chart for two-artist comparisons.
//
// No charting library dependency. Each axis gets a label and an end-of-
// axis value tag. Each artist contributes a colored polygon (translucent
// fill + solid stroke). Designed for 5-8 axes; more than that crowds.
//
// Values are normalized per-axis to max(a, b) by default so the bigger
// of the two always reaches the outer ring (visceral "who's larger"
// read), or to 0-100 when `normalizeMode="percent"` (used by the
// scoring radar where dimensions are already bounded scores).

export type RadarDim = {
  /** Short label shown next to the axis tip. */
  label: string;
  /** Long-form value for axis tip / tooltip — e.g. "102M". */
  fmt: (n: number) => string;
  valueA: number | null;
  valueB: number | null;
};

type Props = {
  dims: RadarDim[];
  accentA: string;
  accentB: string;
  /**
   * Inner polygon size (the square that the radar grid + polygons
   * draw inside of). Default 320. The SVG viewport itself is wider
   * than this so axis labels have horizontal room without clipping.
   */
  size?: number;
  /**
   * Horizontal padding for axis labels (each side of the chart).
   * Long labels like "Spotify monthly listeners" need ~120px room
   * outside the polygon edge.
   */
  labelPaddingX?: number;
  /**
   * "max"     — each axis scaled to max(valueA, valueB) (default)
   * "percent" — axis is 0-100, used for scoring breakdowns
   */
  normalizeMode?: "max" | "percent";
};

export function RadarChart({
  dims,
  accentA,
  accentB,
  size = 320,
  labelPaddingX = 130,
  normalizeMode = "max",
}: Props) {
  // SVG viewport: square chart + horizontal slack for labels on both
  // sides. The polygon stays centered on (size/2 + labelPaddingX, size/2).
  const viewBoxW = size + labelPaddingX * 2;
  const viewBoxH = size + 40;  // small vertical pad for top/bottom labels
  const cx = viewBoxW / 2;
  const cy = viewBoxH / 2;
  // Polygon radius — leave 30px between outer ring and the SVG content
  // bounds; the labels live in `labelPaddingX` past that.
  const radius = size / 2 - 30;
  const n = dims.length;
  if (n === 0) return null;

  // Each axis sits at -90deg + (i * 360/n). -90 puts the first axis
  // at 12 o'clock, which is the conventional radar orientation.
  const angles = Array.from({ length: n }, (_, i) => (-Math.PI / 2) + (i * 2 * Math.PI) / n);

  // Per-axis max — controls how each axis is independently scaled.
  // Required because the dimensions have very different magnitudes
  // (102M listeners vs 5 releases would otherwise flatten one polygon).
  const maxPerAxis = dims.map((d) => {
    if (normalizeMode === "percent") return 100;
    return Math.max(d.valueA ?? 0, d.valueB ?? 0, 1);
  });

  // Compute the (x, y) for value `v` on axis `i`.
  const pointFor = (i: number, v: number | null): [number, number] => {
    if (v == null) return [cx, cy];
    const r = (v / maxPerAxis[i]) * radius;
    return [cx + r * Math.cos(angles[i]), cy + r * Math.sin(angles[i])];
  };

  const polygonPath = (key: "valueA" | "valueB"): string => {
    const pts = dims.map((d, i) => pointFor(i, d[key]));
    return pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") + " Z";
  };

  // Concentric grid rings — 5 levels (20%, 40%, ..., 100% of radius).
  const ringPaths = [0.2, 0.4, 0.6, 0.8, 1.0].map((frac) => {
    const r = radius * frac;
    return dims
      .map((_, i) => {
        const x = cx + r * Math.cos(angles[i]);
        const y = cy + r * Math.sin(angles[i]);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ") + " Z";
  });

  // Axis lines from center to each tip
  const axisLines = dims.map((_, i) => {
    const [x, y] = pointFor(i, maxPerAxis[i]);
    return { x1: cx, y1: cy, x2: x, y2: y };
  });

  // Label positions — slightly outside the outer ring.
  const labelPositions = dims.map((d, i) => {
    const r = radius + 18;
    const x = cx + r * Math.cos(angles[i]);
    const y = cy + r * Math.sin(angles[i]);
    // text-anchor heuristic — align based on angle so labels don't crowd center.
    const cos = Math.cos(angles[i]);
    const anchor = cos > 0.2 ? "start" : cos < -0.2 ? "end" : "middle";
    return { x, y, label: d.label, anchor, dim: d };
  });

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${viewBoxW} ${viewBoxH}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Comparison radar chart"
      className="cmp-radar-svg"
    >
      {/* Grid rings (light gray) */}
      {ringPaths.map((path, i) => (
        <path
          key={`ring-${i}`}
          d={path}
          fill="none"
          stroke="#e5e5e0"
          strokeWidth={1}
        />
      ))}
      {/* Axis lines */}
      {axisLines.map((l, i) => (
        <line
          key={`axis-${i}`}
          x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke="#e5e5e0"
          strokeWidth={1}
        />
      ))}
      {/* Polygon B (drawn first so A overlays it). Renders only when at
          least one value is non-null — collapsed polygons at the center
          add no information and look like noise. */}
      {dims.some((d) => d.valueB != null) && (
        <path
          d={polygonPath("valueB")}
          fill={accentB}
          fillOpacity={0.18}
          stroke={accentB}
          strokeWidth={1.5}
        />
      )}
      {dims.some((d) => d.valueA != null) && (
        <path
          d={polygonPath("valueA")}
          fill={accentA}
          fillOpacity={0.18}
          stroke={accentA}
          strokeWidth={1.5}
        />
      )}
      {/* Vertex dots — small filled circles on each polygon vertex */}
      {dims.map((d, i) => {
        const out: React.ReactNode[] = [];
        if (d.valueA != null) {
          const [x, y] = pointFor(i, d.valueA);
          out.push(<circle key={`a-${i}`} cx={x} cy={y} r={3} fill={accentA} />);
        }
        if (d.valueB != null) {
          const [x, y] = pointFor(i, d.valueB);
          out.push(<circle key={`b-${i}`} cx={x} cy={y} r={3} fill={accentB} />);
        }
        return out;
      })}
      {/* Axis labels */}
      {labelPositions.map((p, i) => (
        <text
          key={`label-${i}`}
          x={p.x}
          y={p.y}
          textAnchor={p.anchor as "start" | "middle" | "end"}
          dominantBaseline="middle"
          className="cmp-radar-label"
        >
          {p.label}
        </text>
      ))}
    </svg>
  );
}
