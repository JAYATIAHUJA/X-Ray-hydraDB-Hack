import type { SVGProps } from "react";
export type IconName = "overview" | "risk" | "ask" | "graph" | "import" | "action" | "settings" | "search" | "filter" | "external" | "close" | "database";
export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  const common = { fill: "none", stroke: "currentColor", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, strokeWidth: 1.8 };
  return <svg aria-hidden="true" viewBox="0 0 24 24" {...props} {...common}>
    {name === "overview" ? <><path d="M4 11 12 4l8 7"/><path d="M6.5 10v10h11V10M9.5 20v-6h5v6"/></> : null}
    {name === "risk" ? <><path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4.5M12 17h.01"/></> : null}
    {name === "ask" ? <><path d="M5 5.5h14v10H9l-4 3v-13Z"/><path d="M9 9h6M9 12h4"/></> : null}
    {name === "graph" ? <><circle cx="6" cy="7" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="15" cy="18" r="2.5"/><circle cx="5" cy="17" r="2.5"/><path d="m8.4 6.8 7.1-.5M7.2 9.1l6.5 6.8M7.4 16.9l5.1.7M17.2 8.4l-1.5 7.1"/></> : null}
    {name === "import" ? <><path d="M12 3v12M7.5 10.5 12 15l4.5-4.5"/><path d="M4 19v2h16v-2"/></> : null}
    {name === "action" ? <><path d="M8 4h8M9 2h6v4H9z"/><path d="M6 4H4v18h16V4h-2M8 11h8M8 16h5"/></> : null}
    {name === "settings" ? <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.5 1a8 8 0 0 0-2-1.2L14 3h-4l-.4 2.6a8 8 0 0 0-2 1.2l-2.5-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.5-1a8 8 0 0 0 2 1.2L10 21h4l.4-2.6a8 8 0 0 0 2-1.2l2.5 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z"/></> : null}
    {name === "search" ? <><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></> : null}
    {name === "filter" ? <path d="M4 5h16l-6.3 7.1V19l-3.4 2v-8.9L4 5Z"/> : null}
    {name === "external" ? <><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v7H4V6h7"/></> : null}
    {name === "close" ? <path d="m6 6 12 12M18 6 6 18"/> : null}
    {name === "database" ? <><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/></> : null}
  </svg>;
}
