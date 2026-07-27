<template>
  <main class="slidev-layout hd-split">
    <section class="hd-split-copy">
      <slot />
    </section>
    <section class="hd-split-visual">
      <slot name="right" />
    </section>
  </main>
</template>

<style>
.hd-split {
  display: grid;
  align-items: center;
  padding: 68px 76px;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 64px;
}

.hd-split-copy,
.hd-split-visual {
  min-width: 0;
}

.hd-split h1 {
  font-size: 50px;
}
</style>
