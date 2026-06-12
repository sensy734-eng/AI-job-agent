export function cn(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function scoreLabel(score: number) {
  if (score >= 85) return "高度匹配";
  if (score >= 70) return "较匹配";
  if (score >= 55) return "可优化";
  return "需补强";
}
