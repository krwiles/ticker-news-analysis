/* Multiple-choice quiz widget shared by lessons. Markup:
   <div class="mcq"><p class="q">…</p>
     <button class="opt" data-correct="true|false" data-why="explanation">option text</button> …</div>
   Click an option: instant feedback with its own explanation; a wrong pick stays retryable,
   the right pick locks the question. Keep every option about the same length so length
   never hints at the answer. */
document.querySelectorAll(".mcq").forEach((quiz) => {
  // The feedback line is created here so lesson markup only needs the question and options.
  const feedback = document.createElement("p");
  feedback.className = "mcq-feedback";
  feedback.hidden = true;
  quiz.appendChild(feedback);
  const options = quiz.querySelectorAll(".opt");
  options.forEach((option) => {
    option.addEventListener("click", () => {
      // Clear any earlier wrong pick's styling before judging this one.
      options.forEach((o) => o.classList.remove("wrong", "right"));
      const isRight = option.dataset.correct === "true";
      option.classList.add(isRight ? "right" : "wrong");
      // Show why this option is right or wrong, not just that it is.
      feedback.hidden = false;
      feedback.textContent = (isRight ? "Correct. " : "Not quite. ") + option.dataset.why;
      // A correct answer locks the question so the result stays readable.
      if (isRight) options.forEach((o) => (o.disabled = true));
    });
  });
});
