import { defineStore } from "pinia";
import { ref } from "vue";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(sessionStorage.getItem("sop_token"));
  const user = ref<{ id: number; name: string; role: string } | null>(null);

  function setToken(t: string) {
    token.value = t;
    sessionStorage.setItem("sop_token", t);
  }

  function logout() {
    token.value = null;
    user.value = null;
    sessionStorage.removeItem("sop_token");
  }

  return { token, user, setToken, logout };
});
