"use client";

import dynamic from "next/dynamic";

const UnicornScene = dynamic(() => import("unicornstudio-react/next"), {
  ssr: false,
});

export default function AsciiUnicorn() {
  return (
    <div className="absolute bottom-0 left-0 right-0 h-[40vh] z-0 pointer-events-none">
      <UnicornScene
        projectId="sTmFbEvSZWihhi3Y1Fro"
        scale={1}
        dpi={1.5}
        fps={60}
        production
      />
    </div>
  );
}
