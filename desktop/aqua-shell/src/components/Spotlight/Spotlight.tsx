import { useRef } from "react";

interface Props {
  onClose: () => void;
}

export default function Spotlight({ onClose }: Readonly<Props>) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const query = inputRef.current?.value.trim();
    if (!query) return;
    console.log("[Spotlight] search:", query);
    onClose();
  };

  return (
    <div
      className="spotlight-overlay"
    >
      <form className="spotlight glass" onSubmit={handleSearch}>
        <input
          ref={inputRef}
          className="spotlight__input"
          type="text"
          placeholder="Search apps, files, or ask Kryos AI…"
          autoFocus
          spellCheck={false}
        />
      </form>
    </div>
  );
}
