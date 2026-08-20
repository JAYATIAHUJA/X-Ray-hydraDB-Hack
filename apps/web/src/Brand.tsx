export function XRayLogo({ className = "" }: { className?: string }) {
  return (
    <svg className={`xray-logo ${className}`} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect className="xray-logo-bg" x="2" y="2" width="36" height="36" rx="10" />
      <path className="xray-logo-frame" d="M10.5 15v-4.5H15M25 10.5h4.5V15M29.5 25v4.5H25M15 29.5h-4.5V25" />
      <circle className="xray-logo-scan" cx="20" cy="20" r="8.25" />
      <path className="xray-logo-ray" d="m13.7 13.7 3.7 3.7m8.9-3.7-3.7 3.7m3.7 8.9-3.7-3.7m-8.9 3.7 3.7-3.7" />
      <circle className="xray-logo-core" cx="20" cy="20" r="3.5" />
      <circle className="xray-logo-dot" cx="20" cy="20" r="1.15" />
    </svg>
  );
}
