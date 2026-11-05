import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { QueryPage } from "./features/query/QueryPage";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <QueryPage />
    </QueryClientProvider>
  );
}
