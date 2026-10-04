import { describe,expect,it } from "vitest";
import { render,screen } from "@testing-library/react";
import { Badge,Card,Metric } from "./ui";
describe("Figma workspace UI primitives",()=>{it("renders card and metric",()=>{render(<><Metric label="Filed claims" value="12" note="Current"/> <Card><Badge tone="success">Active</Badge></Card></>);expect(screen.getByText("Filed claims")).toBeInTheDocument();expect(screen.getByText("12")).toBeInTheDocument();expect(screen.getByText("Active")).toBeInTheDocument()})});
