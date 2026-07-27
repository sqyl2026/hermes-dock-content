<template>
  <main class="slidev-layout hd-metric">
    <div class="hd-metric-content">
      <slot />
    </div>
  </main>
</template>

<style>
.hd-metric {
  display: flex;
  align-items: center;
  padding: 72px 82px;
  background:
    radial-gradient(circle at 82% 22%, rgb(255 180 84 / 16%), transparent 34%),
    var(--deck-bg);
}

.hd-metric-content {
  width: 100%;
}

.hd-metric h1 {
  max-width: 980px;
  font-size: 52px;
}
</style>
