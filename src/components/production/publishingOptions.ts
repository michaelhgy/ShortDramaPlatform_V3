// Fixed minute presets from Xiao V Cat's scheduled "作品间隔"; custom is also supported there.
export const intervalMinutes = [0, 1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 90, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720, 1440, 2160, 2880];
export function intervalLabel(minutes: number) {
  return minutes === 0 ? '无间隔' : minutes < 60 ? `${minutes}分钟` : `${minutes / 60}小时`;
}
export const declarationOptions = [
  { value: 0, label: '无需声明' }, { value: 1, label: '含AI生成内容' },
  { value: 3, label: '内容为虚构剧情，仅供娱乐' }, { value: 8, label: '个人观点，仅供参考' },
  { value: 2, label: '内容包含营销广告' }, { value: 5, label: '内容为自行拍摄' }, { value: 7, label: '内容为转载' },
];
