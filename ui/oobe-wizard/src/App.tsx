import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

const FALLBACK_MODELS = ["llama3-8b", "mistral-7b", "phi-4", "gemma-3-12b"];

type WizardState = {
  timezone: string;
  language: "English" | "Spanish" | "French" | "German" | "Japanese";
  keyboard: "US" | "UK" | "German" | "French" | "Japanese";
  fullName: string;
  username: string;
  password: string;
  confirmPassword: string;
  avatar: string;
  allowCloud: boolean;
  model: string;
  hfUrl: string;
};

const AVATARS = ["A", "B", "C", "D", "E", "F"];

function slugifyUsername(name: string): string {
  const slug = name
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "_")
    .replaceAll(/^_+|_+$/g, "")
    .slice(0, 20);
  return slug.length >= 3 ? slug : "kryos_user";
}

function groupedTimezones(): Record<string, string[]> {
  const list = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["UTC"];
  return list.reduce<Record<string, string[]>>((acc, tz) => {
    const [region] = tz.split("/");
    if (!acc[region]) acc[region] = [];
    acc[region].push(tz);
    return acc;
  }, {});
}

export default function App() {
  const [step, setStep] = useState(1);
  const [models, setModels] = useState<string[]>(FALLBACK_MODELS);
  const [error, setError] = useState<string>("");
  const [state, setState] = useState<WizardState>({
    timezone: "UTC",
    language: "English",
    keyboard: "US",
    fullName: "",
    username: "kryos_user",
    password: "",
    confirmPassword: "",
    avatar: "A",
    allowCloud: false,
    model: FALLBACK_MODELS[0],
    hfUrl: "",
  });

  const tzGroups = useMemo(() => groupedTimezones(), []);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch("http://localhost:8000/api/models/list");
        if (!res.ok) throw new Error("model list unavailable");
        const data = (await res.json()) as { models?: Array<{ id?: string; name?: string }>; items?: string[] };
        const parsed = data.models?.map((m) => m.id ?? m.name ?? "").filter(Boolean) ?? data.items ?? [];
        if (parsed.length > 0) {
          setModels(parsed);
          setState((prev) => ({ ...prev, model: parsed[0] }));
        }
      } catch {
        setModels(FALLBACK_MODELS);
      }
    })();
  }, []);

  function update<K extends keyof WizardState>(key: K, value: WizardState[K]) {
    setState((prev) => ({ ...prev, [key]: value }));
  }

  async function next() {
    setError("");
    if (step === 3) {
      if (!/^[a-z0-9_]{3,20}$/.test(state.username)) {
        setError("Username must be lowercase letters, numbers, or underscores (3-20 chars).");
        return;
      }
      if (state.password !== state.confirmPassword) {
        setError("Passwords do not match.");
        return;
      }
    }

    if (step === 4 && state.hfUrl.trim()) {
      try {
        await fetch("http://localhost:8000/api/models/load", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: "huggingface", url: state.hfUrl.trim() }),
        });
      } catch {
        // Fire-and-forget fallback for first boot.
      }
    }

    setStep((v) => Math.min(5, v + 1));
  }

  function back() {
    setError("");
    setStep((v) => Math.max(1, v - 1));
  }

  async function finish() {
    const payload = {
      user: { name: state.fullName, username: state.username, avatar: state.avatar },
      ai: { model: state.model, allow_cloud: state.allowCloud },
      locale: { timezone: state.timezone, language: state.language, keyboard: state.keyboard },
    };

    try {
      await fetch("http://localhost:8001/api/soul/init", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      // Continue to config write even if soul endpoint is down.
    }

    await fetch("http://localhost:8099/api/oobe/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    globalThis.location.href = "http://localhost:3000";
  }

  return (
    <div className="app-shell">
      <div className="panel">
        <div className="header">
          <strong>PradyOS Setup</strong>
          <div className="progress" aria-label="Progress">
            {[1, 2, 3, 4, 5].map((i) => (
              <span key={i} className={i <= step ? "active" : ""} />
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            className="content"
            initial={{ x: 90, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -90, opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            {step === 1 && (
              <>
                <svg className="logo" viewBox="0 0 120 120" aria-hidden="true">
                  <defs>
                    <linearGradient id="logoStroke" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#68d6ff" />
                      <stop offset="100%" stopColor="#69f5ba" />
                    </linearGradient>
                  </defs>
                  <circle cx="60" cy="60" r="50" fill="none" stroke="url(#logoStroke)" strokeWidth="8">
                    <animate attributeName="stroke-dasharray" values="0,314;157,157" dur="1.4s" fill="freeze" />
                  </circle>
                </svg>
                <h1>Hello.</h1>
                <p>Let's get your AI desktop ready.</p>
              </>
            )}

            {step === 2 && (
              <>
                <h2>Region &amp; Language</h2>
                <div className="grid-2">
                  <label className="field">
                    <span>Timezone</span>
                    <select
                      aria-label="Timezone"
                      value={state.timezone}
                      onChange={(e) => update("timezone", e.target.value)}
                    >
                      {Object.entries(tzGroups).map(([region, zones]) => (
                        <optgroup key={region} label={region}>
                          {zones.map((z) => (
                            <option key={z} value={z}>
                              {z}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Language</span>
                    <select
                      aria-label="Language"
                      value={state.language}
                      onChange={(e) => update("language", e.target.value as WizardState["language"])}
                    >
                      {["English", "Spanish", "French", "German", "Japanese"].map((lang) => (
                        <option key={lang} value={lang}>
                          {lang}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="field">
                  <span>Keyboard Layout</span>
                  <select
                    aria-label="Keyboard Layout"
                    value={state.keyboard}
                    onChange={(e) => update("keyboard", e.target.value as WizardState["keyboard"])}
                  >
                    {["US", "UK", "German", "French", "Japanese"].map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}

            {step === 3 && (
              <>
                <h2>User Account</h2>
                <div className="grid-2">
                  <label className="field">
                    <span>Full Name</span>
                    <input
                      aria-label="Full Name"
                      value={state.fullName}
                      onChange={(e) => {
                        const fullName = e.target.value;
                        update("fullName", fullName);
                        update("username", slugifyUsername(fullName));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>Username</span>
                    <input
                      aria-label="Username"
                      value={state.username}
                      onChange={(e) => update("username", e.target.value)}
                    />
                  </label>
                </div>

                <div className="grid-2">
                  <label className="field">
                    <span>Password</span>
                    <input
                      aria-label="Password"
                      type="password"
                      value={state.password}
                      onChange={(e) => update("password", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Confirm Password</span>
                    <input
                      aria-label="Confirm Password"
                      type="password"
                      value={state.confirmPassword}
                      onChange={(e) => update("confirmPassword", e.target.value)}
                    />
                  </label>
                </div>

                <div className="field">
                  <span>Avatar</span>
                  <div className="avatar-row">
                    {AVATARS.map((avatar) => (
                      <button
                        key={avatar}
                        type="button"
                        aria-label={`Avatar ${avatar}`}
                        className={`avatar-btn ${state.avatar === avatar ? "active" : ""}`}
                        onClick={() => update("avatar", avatar)}
                      >
                        {avatar}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            {step === 4 && (
              <>
                <h2>Set up your AI brain</h2>
                <label className="field">
                  <span>Inference Mode</span>
                  <select
                    aria-label="Inference Mode"
                    value={state.allowCloud ? "cloud" : "local"}
                    onChange={(e) => update("allowCloud", e.target.value === "cloud")}
                  >
                    <option value="local">Use local AI only (private)</option>
                    <option value="cloud">Allow cloud AI (faster)</option>
                  </select>
                </label>

                <label className="field">
                  <span>Default Model</span>
                  <select
                    aria-label="Default Model"
                    value={state.model}
                    onChange={(e) => update("model", e.target.value)}
                  >
                    {models.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span>Add a custom model from HuggingFace</span>
                  <input
                    aria-label="HuggingFace URL"
                    placeholder="https://huggingface.co/..."
                    value={state.hfUrl}
                    onChange={(e) => update("hfUrl", e.target.value)}
                  />
                </label>

                <p>You can change this anytime in Settings.</p>
              </>
            )}

            {step === 5 && (
              <>
                <svg width="92" height="92" viewBox="0 0 120 120" aria-label="Success Checkmark">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="8" />
                  <path
                    d="M34 62 L52 80 L86 42"
                    fill="none"
                    stroke="#69f5ba"
                    strokeWidth="10"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ strokeDasharray: 90, strokeDashoffset: 90, animation: "draw 0.7s ease forwards" }}
                  />
                </svg>
                <h2>You're all set.</h2>
                <div className="summary">
                  <span>Username: {state.username}</span>
                  <span>Timezone: {state.timezone}</span>
                  <span>Default model: {state.model}</span>
                </div>
              </>
            )}

            {error && <div className="error">{error}</div>}
          </motion.div>
        </AnimatePresence>

        <div className="footer">
          {step > 1 ? (
            <button type="button" className="btn secondary" onClick={back}>
              Back
            </button>
          ) : (
            <span />
          )}

          {step < 5 ? (
            <button type="button" className="btn primary" onClick={next}>
              {step === 1 ? "Get Started →" : "Continue"}
            </button>
          ) : (
            <button type="button" className="btn primary" onClick={finish}>
              Start Using PradyOS
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
