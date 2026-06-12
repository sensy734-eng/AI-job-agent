import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 求职助手 Agent",
  description: "基于简历和岗位 JD 的 AI 求职助手产品原型"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
