import fs from "node:fs";
import path from "node:path";

/**
 * Explicit single-session persistence (BR-14): one session id in
 * viz-shell/.cache/session.json, resumed every turn, reset by "New chat".
 */
export class SessionStore {
  constructor(private readonly filePath: string) {}

  get id(): string | null {
    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      const parsed: unknown = JSON.parse(raw);
      const id = (parsed as { id?: unknown })?.id;
      return typeof id === "string" && id.length > 0 ? id : null;
    } catch {
      return null; // missing/corrupt file = no session (fail-honest)
    }
  }

  set(id: string): void {
    const dir = path.dirname(this.filePath);
    fs.mkdirSync(dir, { recursive: true });
    const tmp = path.join(dir, `.session.${process.pid}.tmp`);
    fs.writeFileSync(tmp, JSON.stringify({ id, createdAt: new Date().toISOString() }));
    fs.renameSync(tmp, this.filePath); // atomic swap
  }

  reset(): void {
    try {
      fs.unlinkSync(this.filePath);
    } catch {
      // already absent — fine
    }
  }
}
