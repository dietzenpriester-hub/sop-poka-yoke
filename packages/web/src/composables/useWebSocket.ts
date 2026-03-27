import { onUnmounted, ref, type Ref } from "vue";

export type WsMessageHandler = (data: unknown) => void;

export function useStationWebSocket(
  stationId: string,
  onMessage: WsMessageHandler,
  apiBaseWs: string = import.meta.env.VITE_WS_BASE || "ws://localhost:8000"
): { send: (obj: unknown) => void; ready: Ref<boolean> } {
  const ready = ref(false);
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    ws = new WebSocket(`${apiBaseWs}/api/ws/live/${stationId}`);
    ws.onopen = () => {
      ready.value = true;
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        onMessage(data);
      } catch {
        onMessage(event.data);
      }
    };
    ws.onclose = () => {
      ready.value = false;
      timer = setTimeout(connect, 3000);
    };
  };

  connect();

  onUnmounted(() => {
    if (timer) clearTimeout(timer);
    ws?.close();
  });

  const send = (obj: unknown) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  };

  return { send, ready };
}
