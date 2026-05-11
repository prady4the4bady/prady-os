import { useCallback, useEffect, useState } from "react";

const SWARM_BASE = (import.meta.env as Record<string, string>)
  .VITE_SWARM_URL ?? "http://localhost:8000";

interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
}

type Scale = 1 | 0.5 | 0.25;

export function ScreenViewer() {
  const [image, setImage] = useState<string>("");
  const [ocr, setOcr] = useState<string[]>([]);
  const [scale, setScale] = useState<Scale>(1);
  const [boxes, setBoxes] = useState<BBox[]>([]);
  const [clicking, setClicking] = useState(false);
  const scaleLabel = (value: Scale): string => {
    if (value === 1) return "1x";
    if (value === 0.5) return "½x";
    return "¼x";
  };

  useEffect(() => {
    let mounted = true;
    async function tick() {
      try {
        const res = await fetch(`${SWARM_BASE}/input/screenshot`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { image_b64?: string; ocr_text?: string[] };
        if (!mounted) return;
        setImage(data.image_b64 ?? "");
        setOcr(data.ocr_text ?? []);
      } catch {
        if (!mounted) return;
        setImage("");
      }
    }

    void tick();
    const timer = globalThis.setInterval(() => void tick(), 500);
    return () => {
      mounted = false;
      globalThis.clearInterval(timer);
    };
  }, []);

  const handleClick = useCallback(
    async (e: React.MouseEvent<HTMLButtonElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = Math.round((e.clientX - rect.left) / scale);
      const y = Math.round((e.clientY - rect.top) / scale);
      setClicking(true);
      try {
        await fetch(`${SWARM_BASE}/input/action`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "click", params: { x, y } }),
        });
      } finally {
        setClicking(false);
      }
    },
    [scale]
  );

  return (
    <div className="h-full p-3 flex flex-col gap-3 text-sm">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Screen Viewer</div>
        <div className="flex items-center gap-2">
          {([1, 0.5, 0.25] as Scale[]).map((s) => (
            <button
              key={s}
              onClick={() => setScale(s)}
              className={`px-2 py-0.5 rounded text-xs ${
                scale === s
                  ? "bg-blue-500 text-white"
                  : "bg-white/20 hover:bg-white/30"
              }`}
            >
              {scaleLabel(s)}
            </button>
          ))}
          {clicking && <span className="text-xs text-blue-400 animate-pulse">Clicking…</span>}
        </div>
      </div>

      <div className="relative flex-1 rounded-xl bg-black/30 overflow-hidden">
        {image ? (
          <div className="relative inline-block w-full h-full">
            <button
              type="button"
              data-testid="screen-image"
              className="w-full h-full block p-0 m-0 border-0 bg-transparent cursor-crosshair"
              onClick={handleClick}
              aria-label="Click screen"
            >
              <img
                className="w-full h-full object-contain"
                style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
                src={`data:image/png;base64,${image}`}
                alt="Live screen"
              />
            </button>
            {/* Bounding box overlays */}
            {boxes.map((box) => (
              <div
                key={`${box.x}-${box.y}-${box.width}-${box.height}-${box.label ?? ""}`}
                className="absolute border-2 border-yellow-400 pointer-events-none"
                style={{
                  left: box.x * scale,
                  top: box.y * scale,
                  width: box.width * scale,
                  height: box.height * scale,
                }}
              >
                {box.label && (
                  <span className="absolute -top-5 left-0 bg-yellow-400 text-black text-xs px-1 rounded">
                    {box.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center opacity-70">
            No frame available
          </div>
        )}
        {ocr.length > 0 && (
          <div className="absolute bottom-2 left-2 right-2 bg-black/60 text-white text-xs rounded p-2 max-h-20 overflow-auto">
            OCR: {ocr.join(" | ")}
          </div>
        )}
      </div>

      <button
        className="text-xs text-zinc-400 hover:text-zinc-200 self-start"
        onClick={() => setBoxes([])}
      >
        Clear overlays
      </button>
    </div>
  );
}

