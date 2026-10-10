/** 产物里用 `**粗体**` 标记要强调的片段，渲染时转成 `<strong>`。
 *
 * ⚠ 为什么抽成共享模块（修订 44）：`Em` 原本只存在于 `BPathPanel.tsx` 且
 * **没有导出**，`EvidenceLadderPanel.tsx` 拿不到 ⇒ 它把产物里的 `**…**`
 * 当**字面量**印出来，读者在页面上看到的是
 * 「改变的是这个\*\*概念\*\*」而不是加粗的「概念」。
 *
 * ⚠ 这不是装饰问题：阶梯的 `claim` 与 `note` 是**判据本身**，
 *   读者要读的就是那句话；`**` 露在外面会让它看起来像没渲染完。
 *
 * 用法：`<Em s={s} />`。没有 `**` 时原样返回，不产生多余 DOM。
 */
export function Em({ s }: { s: string }) {
  const parts = s.split("**");
  if (parts.length < 3) return <>{s}</>;
  return (
    <>
      {parts.map((p, i) => (i % 2 === 1 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>))}
    </>
  );
}

export default Em;