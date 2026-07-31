"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiClient, Project } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function Sidebar() {
  const router = useRouter();
  const params = useParams();
  const activeProjectId = params?.id as string;
  
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [newProjectName, setNewProjectName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const data = await apiClient.getProjects();
        setProjects(data);
      } catch (err) {
        console.error("Failed to fetch projects", err);
      } finally {
        setLoading(false);
      }
    };
    fetchProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    try {
      setIsSubmitting(true);
      const newProject = await apiClient.createProject({ name: newProjectName.trim() });
      setProjects((prev) => [...prev, newProject]);
      setNewProjectName("");
      router.push(`/projects/${newProject.id}`);
    } catch (err) {
      console.error("Failed to create project", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-[240px] flex-shrink-0 flex flex-col border-r border-border bg-sidebar h-full">
      <div className="p-4 border-b border-border">
        <h2 className="text-sm font-semibold mb-3 tracking-tight">AI Consultant</h2>
        <form onSubmit={handleCreateProject} className="flex flex-col gap-2">
          <Input
            type="text"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            placeholder="New Project..."
            disabled={isSubmitting}
            className="h-8 text-sm"
          />
          <Button type="submit" disabled={isSubmitting || !newProjectName.trim()} size="sm" className="w-full">
            {isSubmitting ? "Creating..." : "Create"}
          </Button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <p className="text-xs text-muted-foreground p-2">Loading...</p>
        ) : projects.length === 0 ? (
          <p className="text-xs text-muted-foreground p-2">No projects</p>
        ) : (
          projects.map((project) => (
            <button
              key={project.id}
              onClick={() => router.push(`/projects/${project.id}`)}
              className={`w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors ${
                activeProjectId === project.id
                  ? "bg-primary text-primary-foreground font-medium"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              }`}
            >
              <div className="truncate">{project.name || "Untitled"}</div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
