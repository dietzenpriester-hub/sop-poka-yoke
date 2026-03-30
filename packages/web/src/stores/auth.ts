import { defineStore } from "pinia";
import { ref } from "vue";
import { STORAGE_TOKEN_KEY } from "@/utils/constants";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(sessionStorage.getItem(STORAGE_TOKEN_KEY));

  function setToken(t: string) {
    token.value = t;
    sessionStorage.setItem(STORAGE_TOKEN_KEY, t);
  }

  function logout() {
    token.value = null;
    sessionStorage.removeItem(STORAGE_TOKEN_KEY);
  }

  return { token, setToken, logout };
});
