export interface EncoderStatus {
  encoder: 'h264_nvenc' | 'libx264';
  warning: {
    reason: string;
    action: string;
    diagnostic: string;
  } | null;
}
