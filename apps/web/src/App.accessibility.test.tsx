import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("workspace accessibility contract", () => {
  it("provides landmarks, names, status announcements, and keyboard-ready controls", () => {
    render(<App />);

    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "产品导航" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("等待提问");
    expect(screen.getByLabelText("请输入投资研究问题")).toHaveAttribute(
      "maxlength",
      "500",
    );
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新建对话" })).toHaveAttribute(
      "type",
      "button",
    );
  });
});
