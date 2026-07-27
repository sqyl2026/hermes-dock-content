<template>
  <main class="slidev-layout hd-section">
    <div class="hd-section-content">
      <slot />
    </div>
  </main>
</template>

<style>
.hd-section {
  display: flex;
  align-items: center;
  padding: 76px 82px;
}

.hd-section-content {
  width: 100%;
}

.hd-section h1 {
  max-width: 940px;
  font-size: 70px;
}
</style>
