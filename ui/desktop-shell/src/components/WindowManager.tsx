import { useMemo } from "react";
import Draggable from "react-draggable";
import { ResizableBox } from "react-resizable";
import type { ResizeCallbackData } from "react-resizable";
import "react-resizable/css/styles.css";
import type { WindowItem } from "../types";

interface Props {
  windows: WindowItem[];
  activeWindowId: string | null;
  onFocus: (id: string) => void;
  onClose: (id: string) => void;
  onMinimize: (id: string) => void;
  onMaximize: (id: string) => void;
  onMoveResize: (id: string, next: Partial<WindowItem>) => void;
  renderWindow: (window: WindowItem) => React.ReactNode;
}

export function WindowManager({
  windows,
  activeWindowId,
  onFocus,
  onClose,
  onMinimize,
  onMaximize,
  onMoveResize,
  renderWindow,
}: Readonly<Props>) {
  const visibleWindows = useMemo(() => windows.filter((w) => !w.minimized), [windows]);

  return (
    <div className="absolute inset-0 pt-6 pb-28 z-20">
      {visibleWindows.map((window) => {
        const focused = activeWindowId === window.id;
        if (window.maximized) {
          return (
            <dialog
              key={window.id}
              data-testid={`window-${window.appId}`}
              className="window-enter absolute inset-6 glass rounded-2xl overflow-hidden"
              style={{ zIndex: window.zIndex }}
              open
            >
              <TitleBar
                title={window.title}
                onClose={() => onClose(window.id)}
                onMinimize={() => onMinimize(window.id)}
                onMaximize={() => onMaximize(window.id)}
              />
              <div className="h-[calc(100%-40px)]">{renderWindow(window)}</div>
            </dialog>
          );
        }

        return (
          <Draggable
            key={window.id}
            handle={`#title-${window.id}`}
            position={{ x: window.x, y: window.y }}
            onStart={() => onFocus(window.id)}
            onStop={(_, data) => onMoveResize(window.id, { x: data.x, y: data.y })}
          >
            <dialog
              data-testid={`window-${window.appId}`}
              className={`window-enter absolute glass rounded-2xl overflow-hidden ${focused ? "ring-2 ring-blue-400/70" : ""}`}
              style={{ zIndex: window.zIndex }}
              open
            >
              <ResizableBox
                width={window.width}
                height={window.height}
                minConstraints={[320, 220]}
                maxConstraints={[1200, 900]}
                onResizeStop={(_, data: ResizeCallbackData) =>
                  onMoveResize(window.id, {
                    width: data.size.width,
                    height: data.size.height,
                  })
                }
              >
                <div className="w-full h-full bg-transparent">
                  <TitleBar
                    id={`title-${window.id}`}
                    title={window.title}
                    onClose={() => onClose(window.id)}
                    onMinimize={() => onMinimize(window.id)}
                    onMaximize={() => onMaximize(window.id)}
                  />
                  <div className="h-[calc(100%-40px)]">{renderWindow(window)}</div>
                </div>
              </ResizableBox>
            </dialog>
          </Draggable>
        );
      })}
    </div>
  );
}

function TitleBar({
  id,
  title,
  onClose,
  onMinimize,
  onMaximize,
}: Readonly<{
  id?: string;
  title: string;
  onClose: () => void;
  onMinimize: () => void;
  onMaximize: () => void;
}>) {
  return (
    <header id={id} className="h-10 px-3 flex items-center justify-between bg-white/45 dark:bg-black/25 cursor-move">
      <div className="flex items-center gap-2">
        <button aria-label="close" className="w-3 h-3 rounded-full bg-red-500" onClick={onClose} />
        <button aria-label="minimize" className="w-3 h-3 rounded-full bg-yellow-400" onClick={onMinimize} />
        <button aria-label="maximize" className="w-3 h-3 rounded-full bg-green-500" onClick={onMaximize} />
      </div>
      <div className="text-xs font-medium">{title}</div>
      <div className="w-12" />
    </header>
  );
}
