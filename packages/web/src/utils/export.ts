import api from "@/api/index";

export async function downloadExcel(
  endpoint: string,
  filename: string,
  params?: Record<string, string | number | undefined>
) {
  const cleanParams: Record<string, string | number> = {};
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        cleanParams[k] = v;
      }
    }
  }

  const { data } = await api.get(endpoint, {
    params: cleanParams,
    responseType: "blob",
    timeout: 60_000,
  });

  const blob = new Blob([data], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
