/** Static SVG keeps the decoration independent of API and application state. */
export default function Sculpture() {
  return <div className="sculpture" aria-hidden="true">
    <svg viewBox="0 0 500 370" focusable="false">
      <defs>
        <linearGradient id="ribbon-sky" x1="0" y1="0" x2="1" y2="1"><stop stopColor="var(--sky)"/><stop offset=".32" stopColor="var(--sky)"/><stop offset=".7" stopColor="var(--ganache)"/><stop offset="1" stopColor="var(--sky)"/></linearGradient>
        <linearGradient id="ribbon-paper" x1="0" y1="0" x2=".8" y2="1"><stop stopColor="var(--paper)"/><stop offset=".45" stopColor="var(--paper)"/><stop offset=".8" stopColor="var(--ganache)"/><stop offset="1" stopColor="var(--paper)"/></linearGradient>
        <linearGradient id="ribbon-fold" x1="0" y1="0" x2="1" y2="0"><stop stopColor="var(--ganache)"/><stop offset="1" stopColor="var(--sky)"/></linearGradient>
        <filter id="contact-shadow" x="-50%" y="-100%" width="200%" height="300%"><feGaussianBlur stdDeviation="14"/></filter>
        <filter id="ribbon-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="2" dy="14" stdDeviation="10" floodColor="var(--ganache)" floodOpacity=".26"/></filter>
        <filter id="ribbon-grain"><feTurbulence type="fractalNoise" baseFrequency=".7" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope=".09"/></feComponentTransfer><feComposite in2="SourceGraphic" operator="in"/><feBlend in2="SourceGraphic" mode="multiply"/></filter>
      </defs>
      <ellipse cx="263" cy="316" rx="140" ry="17" fill="var(--ganache)" opacity=".25" filter="url(#contact-shadow)"/>
      <g transform="rotate(-18 250 190)" filter="url(#ribbon-shadow)"><g filter="url(#ribbon-grain)">
        <path d="M117 237 C36 160 91 42 198 55 C272 63 291 153 245 222 L200 195 C232 143 213 99 179 103 C126 107 120 171 159 202Z" fill="url(#ribbon-sky)"/>
        <path d="M194 100 C230 102 245 150 219 193 L245 222 C288 161 275 91 221 66Z" fill="url(#ribbon-fold)"/>
        <path d="M203 141 C277 58 392 72 414 158 C444 270 319 311 248 263 L276 215 C327 245 374 216 366 178 C358 140 304 128 246 183Z" fill="url(#ribbon-paper)"/>
        <path d="M248 263 C198 243 173 218 143 226 C116 235 118 269 153 281 C211 301 257 259 279 223 L238 191 C212 233 184 249 159 239 C179 254 214 274 248 263Z" fill="url(#ribbon-sky)"/>
        <path d="M114 139 C116 98 153 71 189 76" fill="none" stroke="var(--sky)" strokeOpacity=".5" strokeWidth="2"/>
        <path d="M270 125 C326 99 382 121 388 165" fill="none" stroke="var(--paper)" strokeOpacity=".7" strokeWidth="2"/>
      </g></g>
      <text x="365" y="337" className="sculpture-caption">FIG. 01 / LINKAGE</text>
      <path d="M337 325 L310 292" stroke="var(--ganache)" strokeWidth=".8"/>
    </svg>
  </div>;
}
