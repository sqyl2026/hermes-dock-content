<template>
  <main class="slidev-layout hd-cover">
    <div class="hd-cover-glow" />
    <div class="hd-cover-content">
      <slot />
    </div>
  </main>
</template>

<style>
.hd-cover {
  position: relative;
  display: flex;
  overflow: hidden;
  align-items: flex-end;
  padding: 76px 82px;
}

.hd-cover-content {
  position: relative;
  z-index: 1;
  width: 100%;
}

.hd-cover h1 {
  max-width: 1020px;
  margin-bottom: 28px;
  font-size: 82px;
  line-height: 1.04;
}

.hd-cover-glow {
  position: absolute;
  top: -260px;
  right: -180px;
  width: 760px;
  height: 760px;
  border-radius: 50%;
  background: radial-gradient(circle, rgb(255 180 84 / 26%), transparent 66%);
}
</style>
