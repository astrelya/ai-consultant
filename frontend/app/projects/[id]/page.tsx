import ChatInterface from './ChatInterface';

export default async function ProjectChatPage({ params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    return (
      <div className="flex-1 flex flex-col h-full bg-background overflow-hidden relative">
        <ChatInterface projectId={id} />
      </div>
    );
  } catch (err) {
    return <div className="p-4 text-destructive">Invalid project parameters.</div>;
  }
}
