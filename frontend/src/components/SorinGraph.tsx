import { useMemo } from "react";
import { arc, pie } from "d3";
import type { PieArcDatum } from "d3";
import type { SorinCategory } from "../data/sorin";

type Props = {
  categories: SorinCategory[];
  selectedCategoryId: string;
  onSelectCategory: (category: SorinCategory) => void;
};

const SIZE = 520;
const CENTER = SIZE / 2;
const INNER_RADIUS = 126;
const OUTER_RADIUS = 194;

export default function SorinGraph({ categories, selectedCategoryId, onSelectCategory }: Props) {
  const slices = useMemo(
    () =>
      pie<SorinCategory>()
        .value(() => 1)
        .sort(null)
        .padAngle(0.025)
        .startAngle(-Math.PI / 2)
        .endAngle(Math.PI * 1.5)(categories),
    [categories],
  );

  const selected = categories.find((category) => category.id === selectedCategoryId) ?? categories[0];

  const segmentPath = (datum: PieArcDatum<SorinCategory>, active: boolean) =>
    arc<PieArcDatum<SorinCategory>>()
      .innerRadius(INNER_RADIUS)
      .outerRadius(active ? OUTER_RADIUS + 10 : OUTER_RADIUS)
      .cornerRadius(12)(datum) ?? undefined;

  const labelArc = arc<PieArcDatum<SorinCategory>>()
    .innerRadius((INNER_RADIUS + OUTER_RADIUS) / 2)
    .outerRadius((INNER_RADIUS + OUTER_RADIUS) / 2);

  return (
    <div className="sorin-graph-shell">
      <svg
        className="sorin-graph"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-labelledby="sorin-graph-title sorin-graph-desc"
      >
        <title id="sorin-graph-title">نقشه تعاملی سبد خدمات و محصولات سورین</title>
        <desc id="sorin-graph-desc">
          پنج خانواده اصلی سبد سورین. هر بخش را انتخاب کنید تا خدمات و محصولات همان خانواده نمایش داده شوند.
        </desc>

        <defs>
          <filter id="sorin-ring-shadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="12" stdDeviation="13" floodColor="#02070d" floodOpacity="0.34" />
          </filter>
          <radialGradient id="sorin-ring-core" cx="35%" cy="28%">
            <stop offset="0%" stopColor="#213f4b" />
            <stop offset="100%" stopColor="#101b25" />
          </radialGradient>
        </defs>

        <g transform={`translate(${CENTER}, ${CENTER})`} filter="url(#sorin-ring-shadow)">
          <circle r={OUTER_RADIUS + 29} className="portfolio-orbit" />
          {slices.map((slice) => {
            const category = slice.data;
            const active = category.id === selectedCategoryId;
            const [labelX, labelY] = labelArc.centroid(slice);

            return (
              <g
                key={category.id}
                className={`portfolio-segment ${active ? "active" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`${category.index}، ${category.title}، شامل ${category.offerings.length} مورد`}
                aria-pressed={active}
                onClick={() => onSelectCategory(category)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectCategory(category);
                  }
                }}
              >
                <path d={segmentPath(slice, active)} style={{ "--segment-accent": category.accent } as React.CSSProperties} />
                <text x={labelX} y={labelY} dy="0.36em" textAnchor="middle">
                  {category.index}
                </text>
              </g>
            );
          })}

          <circle r={INNER_RADIUS - 13} className="portfolio-core" />
          <text className="portfolio-core-mark" textAnchor="middle" y="-25">S</text>
          <text className="portfolio-core-title" textAnchor="middle" y="18">{selected.shortTitle}</text>
          <text className="portfolio-core-count" textAnchor="middle" y="49">
            {selected.offerings.length} خدمت و محصول
          </text>
        </g>
      </svg>
    </div>
  );
}
