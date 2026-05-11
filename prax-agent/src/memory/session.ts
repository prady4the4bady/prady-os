import Database from 'better-sqlite3';
import { TaskSession, Macro } from '../types.js';
import * as fs from 'fs';
import * as path from 'path';

export class SessionMemory {
  private db: Database.Database;

  constructor(dbPath: string = '/var/kryos/memory.db') {
    // If not running as root or in /var/kryos, fallback to a local mock DB for testing
    let finalPath = dbPath;
    try {
      fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    } catch {
      finalPath = './mock_memory.db';
    }

    this.db = new Database(finalPath);
    this.initSchema();
  }

  private initSchema() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        status TEXT NOT NULL,
        plan_json TEXT,
        steps_json TEXT,
        summary TEXT,
        started_at INTEGER,
        ended_at INTEGER
      );
      CREATE TABLE IF NOT EXISTS macros (
        id TEXT PRIMARY KEY,
        goal_pattern TEXT NOT NULL,
        steps_json TEXT NOT NULL,
        success_count INTEGER DEFAULT 0,
        created_at INTEGER,
        last_used_at INTEGER
      );
    `);
  }

  saveSession(session: TaskSession): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO sessions 
      (id, goal, status, plan_json, steps_json, summary, started_at, ended_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    stmt.run(
      session.id,
      session.goal,
      session.status,
      JSON.stringify(session.plan || null),
      JSON.stringify(session.executedSteps),
      session.summary || null,
      session.startTime,
      session.endTime || null
    );
  }

  getSession(id: string): TaskSession | null {
    const stmt = this.db.prepare(`SELECT * FROM sessions WHERE id = ?`);
    const row = stmt.get(id) as any;
    if (!row) return null;

    return {
      id: row.id,
      goal: row.goal,
      status: row.status,
      plan: JSON.parse(row.plan_json),
      executedSteps: JSON.parse(row.steps_json),
      summary: row.summary,
      startTime: row.started_at,
      endTime: row.ended_at
    };
  }

  listSessions(limit: number = 10): TaskSession[] {
    const stmt = this.db.prepare(`SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?`);
    const rows = stmt.all(limit) as any[];
    return rows.map(row => ({
      id: row.id,
      goal: row.goal,
      status: row.status,
      executedSteps: JSON.parse(row.steps_json),
      startTime: row.started_at
    }));
  }

  saveMacro(macro: Macro): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO macros 
      (id, goal_pattern, steps_json, success_count, created_at, last_used_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      macro.id,
      macro.goal_pattern,
      macro.steps_json,
      macro.success_count,
      macro.created_at,
      macro.last_used_at
    );
  }

  getStats(): { totalTasks: number, successRate: number, avgDuration: number } {
    const total = (this.db.prepare(`SELECT COUNT(*) as c FROM sessions`).get() as any).c;
    const success = (this.db.prepare(`SELECT COUNT(*) as c FROM sessions WHERE status='completed'`).get() as any).c;
    const avg = (this.db.prepare(`SELECT AVG(ended_at - started_at) as a FROM sessions WHERE ended_at IS NOT NULL`).get() as any).a;
    
    return {
      totalTasks: total,
      successRate: total > 0 ? (success / total) * 100 : 0,
      avgDuration: avg || 0
    };
  }
}
