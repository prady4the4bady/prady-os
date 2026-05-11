import { useEffect, useRef, useState } from "react";
import { useClickOutside } from "../hooks/useClickOutside";

interface Props {
  nemoEnabled: boolean;
}

const APPLE_SVG = (
  <svg width="14" height="14" viewBox="0 0 814 1000" aria-hidden="true" fill="currentColor">
    <path d="M788 775c-11 26-24 50-40 73-22 33-40 56-55 70-23 22-47 33-74 34-19 0-42-5-69-16-28-11-53-16-76-16-24 0-50 5-78 16-28 11-50 17-67 17-26 1-51-10-76-33-16-14-35-38-58-71-25-37-46-80-62-129-18-53-27-104-27-152 0-55 12-103 36-143 19-32 45-58 77-77 32-19 67-29 104-29 20 0 47 6 81 18 33 12 54 18 63 18 7 0 31-7 70-21 37-13 68-18 93-16 69 6 121 33 155 82-62 37-92 88-91 151 1 49 18 89 54 120 16 15 35 26 55 34-4 12-8 23-13 34zM549 18c0 39-14 75-43 109-35 40-77 63-122 59-1-5-2-10-2-16 0-37 16-77 44-110 14-17 33-31 55-41 22-11 43-17 63-19 3 5 5 11 5 18z" />
  </svg>
);

function Clock(): JSX.Element {
  const [time, setTime] = useState(() => new Date());

  useEffect(() => {
    const timer = globalThis.setInterval(() => setTime(new Date()), 1000);
    return () => globalThis.clearInterval(timer);
  }, []);

  return (
    <time dateTime={time.toISOString()}>
      {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
    </time>
  );
}

export function MenuBar({ nemoEnabled }: Readonly<Props>): JSX.Element {
  const [appMenuOpen, setAppMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const menuItems: Array<{ label: string; action?: () => void }> = [
    {
      label: "About PradyOS",
      action: () => {
        globalThis.dispatchEvent(new Event("kryos:open-about"));
        setAppMenuOpen(false);
      },
    },
    { label: "───" },
    {
      label: "First Boot Wizard…",
      action: () => {
        globalThis.dispatchEvent(new Event("kryos:open-oobe"));
        setAppMenuOpen(false);
      },
    },
    {
      label: "System Preferences…",
    },
    { label: "───" },
    { label: "Sleep" },
    { label: "Restart…" },
    { label: "Shut Down…" },
  ];

  useClickOutside(menuRef, () => setAppMenuOpen(false));

  return (
    <header
      className="absolute top-0 left-0 right-0 h-7 px-3 flex items-center justify-between z-50 text-xs select-none"
      style={{
        backdropFilter: "blur(20px) saturate(180%)",
        WebkitBackdropFilter: "blur(20px) saturate(180%)",
        backgroundColor: "rgba(255,255,255,0.72)",
      }}
    >
      <div className="flex items-center gap-4 relative" ref={menuRef}>
        <button
          aria-label="Apple menu"
          className="hover:bg-black/10 rounded px-1 py-0.5 flex items-center"
          onClick={() => setAppMenuOpen((v) => !v)}
        >
          {APPLE_SVG}
        </button>
        <span className="font-semibold">PradyOS</span>
        {(["File", "Edit", "View", "Window", "Help"] as const).map((menu) => (
          <button key={menu} className="hover:bg-black/10 rounded px-1.5 py-0.5">
            {menu}
          </button>
        ))}

        {appMenuOpen ? (
          <div className="absolute top-6 left-0 w-52 rounded-xl shadow-xl border border-black/10 bg-white/90 backdrop-blur-lg py-1 z-[90]">
            {menuItems.map((item, index) => (
              <div
                key={`${item.label}-${index}`}
                className={
                  item.label === "───"
                    ? "border-t border-black/10 my-1"
                    : "px-4 py-1 hover:bg-blue-500 hover:text-white cursor-default rounded-md mx-1"
                }
                onClick={item.action}
              >
                {item.label === "───" ? null : item.label}
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-3">
        <svg width="16" height="12" viewBox="0 0 24 18" fill="currentColor" aria-label="Wi-Fi">
          <path d="M12 18l-4-4.5c1-1 2.4-1.5 4-1.5s3 .5 4 1.5L12 18zm0-12C8 6 4.5 7.5 2 10l2 2c2-2 4.8-3 8-3s6 1 8 3l2-2C19.5 7.5 16 6 12 6zM12 0C6.5 0 1.5 2 0 5l2 2C4 4 7.8 2.5 12 2.5S20 4 22 7l2-2C22.5 2 17.5 0 12 0z" />
        </svg>
        <span aria-label="Battery 100%">🔋</span>
        <span
          title={nemoEnabled ? "Vyrex active" : "Vyrex inactive"}
          className={nemoEnabled ? "text-emerald-600" : "text-zinc-400"}
          aria-label={`Vyrex ${nemoEnabled ? "active" : "inactive"}`}
        >
          🛡
        </span>
        <button
          aria-label="Siri"
          className="w-4 h-4 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 hover:scale-110 transition-transform"
        />
        <Clock />
      </div>
    </header>
  );
}

export default MenuBar;
