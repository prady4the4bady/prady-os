interface Props {
  imageUrl?: string;
  dark?: boolean;
}

export function Wallpaper({ imageUrl, dark = false }: Readonly<Props>) {
  if (imageUrl) {
    return (
      <div
        className="absolute inset-0"
        style={{ backgroundImage: `url(${imageUrl})`, backgroundSize: "cover", backgroundPosition: "center" }}
        aria-hidden="true"
      />
    );
  }

  return (
    <>
      <style>{`
        @keyframes drift {
          0%   { background-position: 0% 50%; }
          50%  { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        .wallpaper-gradient {
          animation: drift 18s ease infinite;
          background-size: 300% 300%;
        }
      `}</style>
      <div
        className="absolute inset-0 wallpaper-gradient"
        aria-hidden="true"
        style={{
          backgroundImage: dark
            ? "radial-gradient(circle at 20% 30%, rgba(60,20,120,0.6), transparent 35%), radial-gradient(circle at 80% 20%, rgba(20,50,140,0.5), transparent 30%), linear-gradient(135deg, #0a0a1a 0%, #1a1040 40%, #0d1a30 100%)"
            : "radial-gradient(circle at 20% 30%, rgba(255,130,180,0.35), transparent 30%), radial-gradient(circle at 80% 20%, rgba(120,170,255,0.35), transparent 25%), linear-gradient(125deg, #f5f5f5 0%, #d7d7ef 35%, #c9d8f8 60%, #f5f5f5 100%)",
        }}
      />
    </>
  );
}
