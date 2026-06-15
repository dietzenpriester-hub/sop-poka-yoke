import axios from "axios";

/**
 * 从 Axios 错误响应中提取用户友好的消息。
 * 支持 FastAPI 的 { detail: string | { msg: string }[] } 格式。
 */
export function parseErrorMsg(e: unknown, fallback: string): string {
  if (!axios.isAxiosError(e)) return fallback;
  const d = e.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length > 0) {
    const first = d[0];
    if (typeof first === "object" && first !== null && "msg" in first) {
      const msg = String((first as { msg: string }).msg);
      if (msg.includes("String should match pattern")) {
        return "产品型号/工序名称仅支持中文、字母、数字、下划线、横杠，可使用单个空格分隔";
      }
      return msg;
    }
  }
  return fallback;
}
