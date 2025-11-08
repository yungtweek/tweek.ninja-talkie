// apps/web/src/app/chat/layout.tsx
'use client'
import ChatProvider from '@/providers/ChatProvider'
import {ReactNode} from "react";
import {StickyComposer} from "@/components/chat/StickyComposer";

export default function ChatLayout({children}: { children: ReactNode }) {
    return <ChatProvider>
        {children}
        <StickyComposer />
    </ChatProvider>
}