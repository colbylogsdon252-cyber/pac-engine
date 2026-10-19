/** Display-only PAC validation status. No network access, credentials or execution controls. */
export class PacValidationStatus extends HTMLElement {
  static observedAttributes = ["status"];
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }
  render() {
    const state = this.getAttribute("status");
    const label = state === "valid" ? "Validation passed" :
      state === "invalid" ? "Validation rejected" : "Validation unavailable";
    const root = this.shadowRoot;
    if (!root) return;
    root.replaceChildren();
    const wrapper = document.createElement("span");
    wrapper.setAttribute("role", "status");
    wrapper.style.cssText = "display:inline-block;padding:6px 10px;border:1px solid currentColor;border-radius:6px;font:inherit";
    wrapper.textContent = "PAC · " + label + " · Not execution authorization";
    root.appendChild(wrapper);
  }
}
if (!customElements.get("pac-validation-status")) {
  customElements.define("pac-validation-status", PacValidationStatus);
}
