import { onUnmounted, ref, watch, isRef, type Ref } from "vue";
import { STORAGE_TOKEN_KEY } from "@/utils/constants";

export type WsMessageHandler = (data: unknown) => void;

export function useStationWebSocket(
  stationId: string | Ref<string>,
  onMessage: WsMessageHandler,
  apiBaseWs: string = import.meta.env.VITE_WS_BASE || `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`
): { send: (obj: unknown) => void; ready: Ref<boolean> } {
  const ready = ref(false);
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let retryCount = 0;
  let intentionalClose = false;
  const MAX_RETRIES = 10;

  const stationIdRef = isRef(stationId) ? stationId : ref(stationId);

  const clearTimer = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const closeSocket = () => {
    clearTimer();
    if (ws) {
      const s = ws;
      ws = null;
      s.onclose = null;
      s.close();
    }
    ready.value = false;
  };

  const connect = () => {
    if (intentionalClose) return;
    const id = String(stationIdRef.value ?? "").trim();
    if (!id) {
      ready.value = false;
      return;
    }
    const token = sessionStorage.getItem(STORAGE_TOKEN_KEY);
    ws = new WebSocket(`${apiBaseWs}/api/ws/live/${encodeURIComponent(id)}`);
    ws.onopen = () => {
      retryCount = 0;
      if (!token) {
        intentionalClose = true;
        ws?.close();
        return;
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ token }));
        ready.value = true;
      }
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        onMessage(data);
      } catch {
        onMessage({ type: "raw", data: event.data });
      }
    };
    ws.onerror = () => {
      ready.value = false;
    };
    ws.onclose = () => {
      ready.value = false;
      if (!intentionalClose && retryCount < MAX_RETRIES) {
        const delay = Math.min(1000 * Math.pow(2, retryCount), 30000);
        retryCount++;
        timer = setTimeout(connect, delay);
      }
    };
  };

  watch(
    stationIdRef,
    () => {
      intentionalClose = true;
      closeSocket();
      intentionalClose = false;
      retryCount = 0;
      connect();
    },
    { immediate: true }
  );

  onUnmounted(() => {
    intentionalClose = true;
    closeSocket();
  });

  const send = (obj: unknown) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  };

  return { send, ready };
}
