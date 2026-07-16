import { useEffect, useMemo, useRef, useState } from "react";
import { hierarchy, linkRadial, tree } from "d3";
import type { HierarchyPointLink, HierarchyPointNode } from "d3";
import type { SorinCategory, SorinOffering } from "../data/sorin";

type GraphDatum = {
  id: string;
  title: string;
  shortTitle: string;
  kind: "root" | "category" | "service" | "product";
  accent: string;
  offering?: SorinOffering;
  children?: GraphDatum[];
};

type Props = {
  categories: SorinCategory[];
  selectedId: string;
  onSelect: (offering: SorinOffering) => void;
};

const MIN_WIDTH = 620;
const HEIGHT = 620;

export default function SorinGraph({ categories, selectedId, onSelect }: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);

  useEffect(() => {
    const element = wrapperRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(MIN_WIDTH, Math.floor(entry.contentRect.width)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const { nodes, links, radius } = useMemo(() => {
    const data: GraphDatum = {
      id: "sorin",
      title: "سورین",
      shortTitle: "سورین",
      kind: "root",
      accent: "#e7f7ff",
      children: categories.map((category) => ({
        id: category.id,
        title: category.title,
        shortTitle: category.shortTitle,
        kind: "category",
        accent: category.accent,
        children: category.offerings.map((offering) => ({
          id: offering.id,
          title: offering.title,
          shortTitle: offering.shortTitle,
          kind: offering.kind,
          accent: offering.accent,
          offering,
        })),
      })),
    };
    const root = hierarchy(data);
    const graphRadius = Math.min(width, HEIGHT) * 0.42;
    tree<GraphDatum>().size([Math.PI * 2, graphRadius])(root);
    return { nodes: root.descendants(), links: root.links(), radius: graphRadius };
  }, [categories, width]);

  const radialLink = linkRadial<HierarchyPointLink<GraphDatum>, HierarchyPointNode<GraphDatum>>()
    .angle((d) => d.x)
    .radius((d) => d.y);

  const point = (node: HierarchyPointNode<GraphDatum>) => {
    const angle = node.x - Math.PI / 2;
    return { x: Math.cos(angle) * node.y, y: Math.sin(angle) * node.y };
  };

  return (
    <div className="sorin-graph-scroll" ref={wrapperRef}>
      <svg
        className="sorin-graph"
        viewBox={`${-width / 2} ${-HEIGHT / 2} ${width} ${HEIGHT}`}
        role="img"
        aria-labelledby="sorin-graph-title sorin-graph-desc"
      >
        <title id="sorin-graph-title">نقشه تعاملی خدمات و محصولات سورین</title>
        <desc id="sorin-graph-desc">برای مشاهده توضیحات هر خدمت یا محصول، گره مربوط به آن را انتخاب کنید.</desc>
        <defs>
          <radialGradient id="sorin-core-glow">
            <stop offset="0%" stopColor="#75d9ff" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#6872ff" stopOpacity="0.45" />
          </radialGradient>
          <filter id="sorin-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <circle r={radius + 28} className="sorin-orbit sorin-orbit-outer" />
        <circle r={radius * 0.55} className="sorin-orbit" />

        <g className="sorin-links">
          {links.map((link) => {
            const target = link.target.data;
            return (
              <path
                key={`${link.source.data.id}-${target.id}`}
                d={radialLink(link) || undefined}
                className={target.id === selectedId ? "active" : ""}
                style={{ "--node-accent": target.accent } as React.CSSProperties}
              />
            );
          })}
        </g>

        <g className="sorin-nodes">
          {nodes.map((node) => {
            const { x, y } = point(node);
            const datum = node.data;
            const interactive = Boolean(datum.offering);
            const selected = datum.id === selectedId;
            const size = datum.kind === "root" ? 56 : datum.kind === "category" ? 36 : 27;
            return (
              <g
                key={datum.id}
                transform={`translate(${x},${y})`}
                className={`sorin-node ${datum.kind} ${selected ? "selected" : ""} ${interactive ? "interactive" : ""}`}
                style={{ "--node-accent": datum.accent } as React.CSSProperties}
                role={interactive ? "button" : undefined}
                tabIndex={interactive ? 0 : undefined}
                aria-label={interactive ? `مشاهده جزئیات ${datum.title}` : undefined}
                aria-pressed={interactive ? selected : undefined}
                onClick={() => datum.offering && onSelect(datum.offering)}
                onKeyDown={(event) => {
                  if (datum.offering && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    onSelect(datum.offering);
                  }
                }}
              >
                {selected && <circle r={size + 10} className="selection-ring" />}
                <circle r={size} className="node-disc" filter={datum.kind === "root" ? "url(#sorin-glow)" : undefined} />
                {datum.kind === "root" ? (
                  <>
                    <text className="root-mark" textAnchor="middle" dy="-1">S</text>
                    <text className="root-label" textAnchor="middle" dy="78">سورین</text>
                  </>
                ) : (
                  <>
                    <text className="node-symbol" textAnchor="middle" dy="5">
                      {datum.kind === "category" ? "◆" : datum.kind === "product" ? "P" : "S"}
                    </text>
                    <text
                      className="node-label"
                      textAnchor={x > 20 ? "start" : x < -20 ? "end" : "middle"}
                      x={x > 20 ? size + 9 : x < -20 ? -size - 9 : 0}
                      y={Math.abs(x) <= 20 ? size + 18 : 5}
                    >
                      {datum.shortTitle}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
