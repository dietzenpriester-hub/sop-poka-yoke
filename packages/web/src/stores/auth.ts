import { defineStore } from "pinia";
import { ref } from "vue";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(null);
  const user = ref<{ id: number; name: string; role: string } | null>(null);

  function setToken(t: string) {
    token.value = t;
  }

  function logout() {
    token.value = null;
    user.value = null;
  }

  return { token, user, setToken, logout };
});
