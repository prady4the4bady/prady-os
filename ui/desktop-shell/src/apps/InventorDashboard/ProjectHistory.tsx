interface Project {
  project_id: string;
  name: string;
  status: string;
  verified: number;
  test_pass_rate: number;
  repo_url: string;
  build_started: string;
  build_completed: string | null;
}

interface ProjectHistoryProps {
  projects: Project[];
}

function statusBadge(status: string, verified: number): { text: string; bg: string; color: string } {
  if (status === "released" && verified) return { text: "Delivered", bg: "#dcfce7", color: "#166534" };
  if (status === "failed") return { text: "Failed", bg: "#fee2e2", color: "#991b1b" };
  if (status === "building" || status === "verifying") return { text: "In Progress", bg: "#dbeafe", color: "#1e40af" };
  if (status === "released") return { text: "Released", bg: "#dcfce7", color: "#166534" };
  return { text: status, bg: "#f3f4f6", color: "#374151" };
}

export default function ProjectHistory({ projects }: Readonly<ProjectHistoryProps>) {
  if (projects.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "#6b7280", fontSize: 14 }}>
        No projects have been built yet. Start the inventor loop to begin.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #e5e7eb", textAlign: "left" }}>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Name</th>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Status</th>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Tests</th>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Verified</th>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Date</th>
            <th style={{ padding: "8px 12px", fontWeight: 600, color: "#374151" }}>Repo</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => {
            const badge = statusBadge(project.status, project.verified);
            return (
              <tr key={project.project_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "10px 12px", fontWeight: 500 }}>{project.name}</td>
                <td style={{ padding: "10px 12px" }}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      borderRadius: 999,
                      padding: "2px 8px",
                      background: badge.bg,
                      color: badge.color,
                    }}
                  >
                    {badge.text}
                  </span>
                </td>
                <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                  {Math.round(project.test_pass_rate * 100)}%
                </td>
                <td style={{ padding: "10px 12px" }}>
                  {project.verified ? "✅ Verified" : "❌ Not Verified"}
                </td>
                <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                  {new Date(project.build_started).toLocaleDateString()}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  {project.repo_url ? (
                    <a
                      href={project.repo_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "#0a84ff", textDecoration: "none" }}
                    >
                      View
                    </a>
                  ) : (
                    <span style={{ color: "#9ca3af" }}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
