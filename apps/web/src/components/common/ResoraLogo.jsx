export function ResoraLogo({ size = 48, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Resora logo"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="5" y="5" width="54" height="54" rx="17" fill="#070B12" stroke="#FF6A00" strokeWidth="3" />
      <rect x="11" y="11" width="42" height="42" rx="13" fill="#020306" stroke="#1A2A42" strokeWidth="1" />
      <path d="M20 41.5 31.5 20 44 41.5H20Z" fill="#FF6A00" opacity="0.22" />
      <path d="M20 41.5 31.5 20 44 41.5" stroke="#FFFFFF" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M24.5 35.5h15" stroke="#00D5FF" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M31.5 20v21.5" stroke="#39FF88" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="31.5" cy="20" r="4.4" fill="#FF6A00" stroke="#FFFFFF" strokeWidth="1.6" />
      <circle cx="20" cy="41.5" r="3.8" fill="#00D5FF" />
      <circle cx="44" cy="41.5" r="3.8" fill="#39FF88" />
      <circle cx="31.5" cy="35.5" r="3.6" fill="#FF174D" stroke="#020306" strokeWidth="1.4" />
    </svg>
  );
}
