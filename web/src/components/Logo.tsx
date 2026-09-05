interface LogoProps {
  className?: string;
  size?: number | string;
  showText?: boolean;
  isDarkTheme?: boolean;
  textSize?: string;
}

export function DealFlowLogo({
  className = "",
  size = 36,
  showText = true,
  isDarkTheme = false,
  textSize = "text-lg",
}: LogoProps) {
  return (
    <div className={`inline-flex items-center gap-3 select-none ${className}`}>
      {/* Exact Vectorized DealFlow360 Emblem */}
      <svg
        width={size}
        height={typeof size === "number" ? size * 0.85 : size}
        viewBox="0 0 110 85"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        {/* Blue 360 loop (Right) */}
        <path
          d="M 68 18 C 84 18 98 30 98 48 C 98 66 84 78 68 78 C 58 78 50 73 45 66 C 41 60 40 54 41 49 C 42 43 45 38 49 34 C 54 29 60 25 67 22"
          stroke="#1d72f2"
          strokeWidth="11"
          strokeLinecap="round"
        />

        {/* Purple 'D' Flow Structure (Left) */}
        <path
          d="M 22 18 H 54 C 70 18 80 30 80 48 C 80 66 70 78 54 78 H 22 V 18 Z"
          stroke="#4b48df"
          strokeWidth="11"
          strokeLinejoin="round"
        />

        {/* Downward Return Flow Arrow on Purple D */}
        <path
          d="M 38 36 V 56 M 30 48 L 38 56 L 46 48"
          stroke="#1d72f2"
          strokeWidth="5.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>

      {/* Brand Typography */}
      {showText && (
        <span
          className={`font-extrabold tracking-tight flex items-center ${textSize} ${
            isDarkTheme ? "text-white drop-shadow-md" : "text-slate-900"
          }`}
        >
          DealFlow<span className="text-[#1d72f2]">360</span>
        </span>
      )}
    </div>
  );
}

export default DealFlowLogo;
