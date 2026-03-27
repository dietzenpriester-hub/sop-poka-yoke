<script setup lang="ts">
defineProps<{
  src: string;
  poster?: string;
}>();
</script>

<template>
  <video :src="src" :poster="poster" controls style="width: 100%; max-height: 480px; border-radius: 8px">
    您的浏览器不支持视频播放
  </video>
</template>
