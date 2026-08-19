import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Graph3D } from "./Graph3D";

const nodes = [
  { key: "person:maya", label: "Maya", size: 100, role: "ghost" as const, focus: true }
];

let frames: FrameRequestCallback[];

beforeEach(() => {
  frames = [];
  vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

function renderGraph(onSelect = vi.fn()) {
  const result = render(
    <Graph3D edges={[]} nodes={nodes} onSelect={onSelect} selectedKey="person:maya" spin={false} />
  );
  const canvas = result.container.querySelector("canvas");
  expect(canvas).not.toBeNull();
  frames.shift()?.(0);
  return { ...result, canvas: canvas as HTMLCanvasElement, onSelect };
}

test("clicking a projected node selects it and hover exposes the pointing state", () => {
  const { canvas, onSelect } = renderGraph();

  fireEvent.pointerMove(canvas, { clientX: 300, clientY: 200 });
  expect(canvas).toHaveClass("is-pointing");

  fireEvent.pointerDown(canvas, { clientX: 300, clientY: 200, pointerId: 1 });
  fireEvent.pointerUp(canvas, { clientX: 300, clientY: 200, pointerId: 1 });
  expect(onSelect).toHaveBeenCalledWith("person:maya");
});

test("dragging rotates without accidentally selecting a node", () => {
  const { canvas, onSelect } = renderGraph();

  fireEvent.pointerDown(canvas, { clientX: 300, clientY: 200, pointerId: 1 });
  fireEvent.pointerMove(canvas, { clientX: 330, clientY: 220, pointerId: 1 });
  fireEvent.pointerUp(canvas, { clientX: 330, clientY: 220, pointerId: 1 });

  expect(onSelect).not.toHaveBeenCalled();
});

test("leaving the canvas clears hover and unmount cancels animation", () => {
  const { canvas, unmount } = renderGraph();
  fireEvent.pointerMove(canvas, { clientX: 300, clientY: 200 });
  fireEvent.pointerLeave(canvas);
  expect(canvas).not.toHaveClass("is-pointing");

  unmount();
  expect(globalThis.cancelAnimationFrame).toHaveBeenCalled();
});
