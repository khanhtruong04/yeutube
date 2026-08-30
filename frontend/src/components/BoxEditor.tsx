"use client";

import { useEffect, useRef, useState } from "react";
import { Rnd } from "react-rnd";

export type EditableBox = {
  id: string;
  xFrac: number;
  yFrac: number;
  wFrac: number;
  hFrac: number;
  tStart: number;
  tEnd: number;
  wholeVideo: boolean;
  borderColor: string;
  label?: string;
};

type Props = {
  videoUrl: string;
  videoWidth: number;
  videoHeight: number;
  boxes: EditableBox[];
  onChangeBox: (id: string, patch: Partial<EditableBox>) => void;
  resizable?: boolean;
};

/** Video + overlay box kéo/resize dùng chung cho MaskEditor và LayoutEditor. */
export default function BoxEditor({ videoUrl, videoWidth, videoHeight, boxes, onChangeBox, resizable = true }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setContainerSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const aspectRatio = videoWidth && videoHeight ? videoWidth / videoHeight : 16 / 9;

  return (
    <div className="w-full max-w-2xl">
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden rounded-lg bg-black"
        style={{ aspectRatio }}
      >
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video src={videoUrl} controls className="absolute inset-0 h-full w-full" />
        {containerSize.width > 0 &&
          boxes.map((box) => (
            <Rnd
              key={box.id}
              bounds="parent"
              enableResizing={resizable}
              size={{ width: box.wFrac * containerSize.width, height: box.hFrac * containerSize.height }}
              position={{ x: box.xFrac * containerSize.width, y: box.yFrac * containerSize.height }}
              onDragStop={(_e, d) => {
                onChangeBox(box.id, {
                  xFrac: clamp01(d.x / containerSize.width),
                  yFrac: clamp01(d.y / containerSize.height),
                });
              }}
              onResizeStop={(_e, _dir, ref, _delta, pos) => {
                onChangeBox(box.id, {
                  wFrac: clamp01(ref.offsetWidth / containerSize.width),
                  hFrac: clamp01(ref.offsetHeight / containerSize.height),
                  xFrac: clamp01(pos.x / containerSize.width),
                  yFrac: clamp01(pos.y / containerSize.height),
                });
              }}
              style={{
                border: `2px solid ${box.borderColor}`,
                background: `${box.borderColor}33`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {box.label && (
                <span className="pointer-events-none select-none truncate px-1 text-xs font-medium text-white [text-shadow:0_1px_2px_black]">
                  {box.label}
                </span>
              )}
            </Rnd>
          ))}
      </div>
    </div>
  );
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}
