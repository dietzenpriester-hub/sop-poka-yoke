<script setup lang="ts">
defineProps<{
  count: number;
  type?: "danger" | "warning" | "info";
}>();
</script>

<template>
  <el-badge :value="count" :type="type || 'danger'" :hidden="count === 0">
    <slot />
  </el-badge>
</template>
