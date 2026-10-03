import { createRoot } from "react-dom/client";
import WitnessApp from "./WitnessApp";

const root = document.getElementById("witness-root");
if (!root) {
  throw new Error("witness-root not found");
}
createRoot(root).render(<WitnessApp />);
