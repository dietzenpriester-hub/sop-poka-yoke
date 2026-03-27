import api from "./index";

export const reportApi = {
  summary: () => api.get("/report/summary"),
};
