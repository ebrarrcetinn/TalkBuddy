// Partner avatarı: tek bir sabit resim. Konuşurken resmin etrafındaki halka hafifçe parlar.
const character = (() => {
  function who(persona) {
    return persona === "Male_Coach" ? "male" : "female";
  }

  // state: idle (dinliyor), talk (konuşuyor), happy (memnun), laugh (gülüyor)
  function render(element, persona, state = "idle") {
    if (element.dataset.persona !== persona || !element.querySelector("img")) {
      const image = document.createElement("img");
      image.src = `/static/images/${who(persona)}.jpg`;
      image.alt = "";
      element.replaceChildren(image);
      element.dataset.persona = persona;
    }
    element.dataset.state = state;
  }

  return { render };
})();
