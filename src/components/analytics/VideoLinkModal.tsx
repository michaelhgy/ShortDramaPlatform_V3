import React, { useState } from 'react';
import { AggregatedPlatformVideo, CandidateClipInfo } from '../../utils/videoEngine';
import { 
  X, 
  Link2, 
  Film, 
  Calendar, 
  Check, 
  AlertCircle,
  FileVideo,
  Sparkles,
  Info
} from 'lucide-react';

interface VideoLinkModalProps {
  video: AggregatedPlatformVideo | null;
  isOpen: boolean;
  onClose: () => void;
  onConfirmLink: (
    videoId: string, 
    clipName: string, 
    materialId: string, 
    materialName: string
  ) => void;
}

export const VideoLinkModal: React.FC<VideoLinkModalProps> = ({
  video,
  isOpen,
  onClose,
  onConfirmLink,
}) => {
  const [selectedClipId, setSelectedClipId] = useState<string>('');
  const [customNote, setCustomNote] = useState<string>('');

  if (!isOpen || !video) return null;

  const candidates: CandidateClipInfo[] = video.candidateClips.length > 0
    ? video.candidateClips
    : [
        {
          clipId: 'clip-01',
          clipName: `${video.dramaName}-01`,
          sourceMaterialId: '素材-01',
          sourceMaterialName: `${video.dramaName}-高光卡点开篇 (01)`,
          duration: '01:05',
          exportDate: `${video.firstObservedDate} 09:30`,
        },
      ];

  const currentSelectedClip = candidates.find((c) => c.clipId === selectedClipId) || candidates[0];

  const handleSave = () => {
    onConfirmLink(
      video.id,
      currentSelectedClip.clipName,
      currentSelectedClip.sourceMaterialId,
      currentSelectedClip.sourceMaterialName
    );
    onClose();
  };

  return (
    <div 
      id="video-link-modal-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div 
        id="video-link-modal-card"
        className="bg-white rounded-2xl w-full max-w-xl shadow-2xl border border-black/10 overflow-hidden space-y-0 animate-in zoom-in-95 duration-150"
      >
        {/* Header */}
        <div className="p-4 bg-[#1A1D2E] text-white flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-white/10 text-[#DDFD00] flex items-center justify-center font-bold">
              <Link2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold">核对平台视频与内部成片关联</h3>
              <p className="text-[11px] text-slate-300">
                将青柠推广视频精确归因至内部导出成片与源素材
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          {/* Target Video Snapshot */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-black/[0.06] space-y-2.5">
            <div className="text-[11px] font-bold text-[#1A1D2E] flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span>平台视频信息 (青柠剧场)</span>
              </div>
              <span className="font-mono text-slate-500 bg-white px-2 py-0.5 rounded border border-black/[0.06]">
                {video.id}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2.5 text-[#64748B] text-[11px]">
              <div>
                账号: <strong className="text-[#1A1D2E]">{video.accountName}</strong>
              </div>
              <div>
                剧集: <strong className="text-[#1A1D2E]">{video.dramaName}</strong>
              </div>
              <div>
                首次观测: <span className="font-mono text-[#1A1D2E]">{video.firstObservedDate}</span>
              </div>
              <div>
                候选批次: <span className="font-mono font-medium text-slate-800">{video.candidateBatch}</span>
              </div>
              <div>
                周期视频播放: <span className="font-mono text-[#1A1D2E]">{video.periodVideoViews.toLocaleString()}</span>
              </div>
              <div>
                周期收益: <strong className="font-mono text-emerald-700 font-bold">¥{video.periodRevenue.toFixed(2)}</strong>
              </div>
            </div>
          </div>

          {/* Association Principle Notice */}
          <div className="flex items-start gap-2 p-2.5 rounded-xl bg-amber-50/90 border border-amber-200/70 text-[11px] text-amber-900 leading-relaxed">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <strong>人工核对原则：</strong>平台仅回传视频 ID，无法完全自动映射内部成片。系统已基于账号、剧集与观测批次推荐以下候选成片，请人工核验画面后确认。
            </div>
          </div>

          {/* Candidate Internal Clips */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="font-bold text-[#1A1D2E] block">
                选择对应的内部成片 (包含源素材信息):
              </label>
              <span className="text-[10px] text-slate-400">已推荐 {candidates.length} 条候选</span>
            </div>
            <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
              {candidates.map((cand) => {
                const isSelected = (selectedClipId || candidates[0].clipId) === cand.clipId;
                return (
                  <div
                    key={cand.clipId}
                    id={`candidate-clip-${cand.clipId}`}
                    onClick={() => setSelectedClipId(cand.clipId)}
                    className={`p-3 rounded-xl border flex items-start justify-between cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-[#1A1D2E] text-white border-[#1A1D2E] shadow-xs'
                        : 'bg-slate-50/80 border-black/[0.06] hover:bg-slate-100/90 text-[#1A1D2E]'
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <FileVideo className={`w-4 h-4 mt-0.5 shrink-0 ${isSelected ? 'text-[#DDFD00]' : 'text-slate-500'}`} />
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs">{cand.clipName}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                            isSelected ? 'bg-white/10 text-slate-200' : 'bg-slate-200/70 text-slate-600'
                          }`}>
                            {cand.duration}
                          </span>
                        </div>
                        <div className={`text-[11px] flex items-center gap-1.5 ${
                          isSelected ? 'text-slate-300' : 'text-[#64748B]'
                        }`}>
                          <span>源素材:</span>
                          <strong className={isSelected ? 'text-[#DDFD00]' : 'text-[#1A1D2E]'}>
                            {cand.sourceMaterialId} · {cand.sourceMaterialName}
                          </strong>
                        </div>
                        <div className={`text-[10px] ${isSelected ? 'text-slate-400' : 'text-slate-400'}`}>
                          成片导出时间: {cand.exportDate}
                        </div>
                      </div>
                    </div>
                    {isSelected && (
                      <div className="p-1 rounded-lg bg-white/10 text-[#DDFD00] shrink-0">
                        <Check className="w-3.5 h-3.5" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Optional Note */}
          <div className="space-y-1">
            <label className="text-[11px] text-[#64748B] block">
              核对说明 (选填):
            </label>
            <input
              type="text"
              placeholder="例如：已核对片头前5秒画面完全一致"
              value={customNote}
              onChange={(e) => setCustomNote(e.target.value)}
              className="w-full px-3 py-1.5 bg-slate-50 border border-black/[0.06] rounded-xl text-xs text-[#1A1D2E] outline-none focus:bg-white focus:border-black/20 transition-all"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-black/[0.06] flex items-center justify-between">
          <div className="text-[11px] text-slate-500 flex items-center gap-1">
            <Info className="w-3.5 h-3.5" />
            <span>建立关联后将用于成片与源素材的收益归因</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-xl text-xs font-medium text-[#64748B] hover:text-[#1A1D2E] hover:bg-black/[0.04] transition-colors"
            >
              取消
            </button>
            <button
              id="confirm-link-btn"
              onClick={handleSave}
              className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs"
            >
              确认建立关联
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
