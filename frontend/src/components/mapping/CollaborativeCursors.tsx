// src/components/mapping/CollaborativeCursors.tsx
import React from 'react';
import { MousePointer2 } from '../icons';
import { useViewport } from 'reactflow';
import type { CollaborativeCursor } from '@/hooks/mapping/useCollaborativeCursors';

interface CollaborativeCursorsProps {
  cursors: CollaborativeCursor[];
}

// Colores para diferentes usuarios (basado en hash del ID)
const CURSOR_COLORS = [
  '#FF6B6B', // Rojo
  '#4ECDC4', // Turquesa
  '#45B7D1', // Azul claro
  '#FFA07A', // Salmón
  '#98D8C8', // Verde menta
  '#F7B731', // Amarillo
  '#5F27CD', // Púrpura
  '#00D2D3', // Cian
  '#FF9FF3', // Rosa
  '#54A0FF', // Azul
];

function getUserColor(userId: string): string {
  // Simple hash para asignar color consistente por usuario
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = userId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return CURSOR_COLORS[Math.abs(hash) % CURSOR_COLORS.length];
}

export const CollaborativeCursors: React.FC<CollaborativeCursorsProps> = ({ cursors }) => {
  // Obtener el viewport actual del usuario que está viendo
  const myViewport = useViewport();

  return (
    <div className="pointer-events-none absolute inset-0 z-50">
      {cursors.map((cursor) => {
        const color = getUserColor(cursor.actorId);

        // Convertir coordenadas del canvas del otro usuario a coordenadas de pantalla
        // para el viewport del usuario actual
        // Fórmula: screenCoord = (canvasCoord * myZoom) + myViewportPosition
        const screenX = (cursor.x * myViewport.zoom) + myViewport.x;
        const screenY = (cursor.y * myViewport.zoom) + myViewport.y;

        return (
          <div
            key={cursor.actorId}
            className="absolute transition-all duration-100 ease-out"
            style={{
              left: `${screenX}px`,
              top: `${screenY}px`,
              transform: 'translate(-2px, -2px)',
            }}
          >
            {/* Cursor icon */}
            <MousePointer2
              className="drop-shadow-lg"
              size={20}
              style={{ color }}
              fill={color}
              strokeWidth={1.5}
            />

            {/* Label con nombre del usuario */}
            <div
              className="absolute top-5 left-2 px-2 py-1 rounded text-xs font-medium text-white whitespace-nowrap shadow-lg"
              style={{
                backgroundColor: color,
              }}
            >
              {cursor.actorName}
            </div>
          </div>
        );
      })}
    </div>
  );
};
