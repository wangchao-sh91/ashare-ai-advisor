import { AppShell } from "./components";
import { ChatWorkspace, useChat } from "./features/chat";

export function App() {
  const chat = useChat();
  return (
    <AppShell onNewChat={chat.reset}>
      <ChatWorkspace chat={chat} />
    </AppShell>
  );
}
