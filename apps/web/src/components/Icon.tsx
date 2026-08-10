import type { SVGProps } from "react";

type IconName =
  | "arrow-up-right"
  | "chat"
  | "check"
  | "chevron-right"
  | "clear"
  | "clock"
  | "external"
  | "fact"
  | "help"
  | "plus"
  | "risk"
  | "send"
  | "sparkle";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

const paths: Record<IconName, React.ReactNode> = {
  "arrow-up-right": <path d="M7 17 17 7M9 7h8v8" />,
  chat: <path d="M6 17.5 3.5 20v-5A8 8 0 1 1 7 18h-1Z" />,
  check: <path d="m5 12 4 4L19 6" />,
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  clear: <path d="M4 7h16M9 7V4h6v3m-9 0 1 13h10l1-13M10 11v5m4-5v5" />,
  clock: <path d="M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />,
  external: (
    <path d="M14 4h6v6m0-6-9 9M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" />
  ),
  fact: (
    <path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" />
  ),
  help: (
    <path d="M9.6 9a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.3 1-1.3 1.8V14m0 3h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  risk: <path d="M12 4 3.8 19h16.4L12 4Zm0 5v4m0 3h.01" />,
  send: <path d="m4 4 17 8-17 8 3-8-3-8Zm3 8h14" />,
  sparkle: (
    <path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" />
  ),
};

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      <g
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      >
        {paths[name]}
      </g>
    </svg>
  );
}
