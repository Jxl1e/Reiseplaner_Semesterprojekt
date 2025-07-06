  function showToast(message, type) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.visibility = 'visible';
    toast.style.opacity = '1';
    toast.style.minWidth = '250px';
    toast.style.backgroundColor = type === 'error' ? '#ce0000' : '#4BB543';
    toast.style.color = 'white';
    toast.style.textAlign = 'center';
    toast.style.borderRadius = '8px';
    toast.style.padding = '12px';
    toast.style.position = 'fixed';
    toast.style.top = '70px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.fontSize = '16px';
    toast.style.zIndex = '9999';
    toast.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
    toast.style.transition = 'opacity 0.5s ease-in-out, visibility 0.5s ease-in-out';
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.visibility = 'hidden';
      setTimeout(() => {
        toast.remove();
      }, 500);
    }, 3000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    window.addEventListener("scroll", () => {
      const footer = document.getElementById("scroll-footer");
      if (!footer) return;

      const scrollTop = window.scrollY;
      const windowHeight = window.innerHeight;
      const bodyHeight = document.documentElement.scrollHeight;

      const scrolledToBottom = scrollTop + windowHeight >= bodyHeight - 5;

      if (scrolledToBottom) {
        footer.classList.add("show");
      } else {
        footer.classList.remove("show");
      }
    });
  });